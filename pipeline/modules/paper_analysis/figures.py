"""Figure image fetching and Gemini vision gene discovery."""

import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests

from .. import config
from .prompts import _FIGURE_ANALYSIS_INSTRUCTION


class FigureMixin:
    def _figure_http_get(self, url: str, **kwargs):
        """GET helper with a short retry for transient figure/CDN failures."""
        attempts = max(1, int(getattr(config, "FIGURE_HTTP_RETRIES", 2)))
        for attempt in range(attempts):
            try:
                return requests.get(url, **kwargs)
            except Exception:
                if attempt + 1 >= attempts:
                    raise
                time.sleep(0.5 * (attempt + 1))
        raise RuntimeError("unreachable figure HTTP retry state")

    def _build_gemini_image_part(self, types_module, image_bytes: bytes, mime_type: str):
        """Construct a Gemini image Part with fallback for library-version differences."""
        try:
            return types_module.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        except Exception:
            try:
                blob = types_module.Blob(data=image_bytes, mime_type=mime_type)
                return types_module.Part(inline_data=blob)
            except Exception:
                return None

    def _resolve_pmc_cdn_url(self, figure: Dict[str, Any]) -> List[str]:
        """Resolve CDN blob URLs for a PMC figure by scraping the article HTML page.

        PMC migrated figure hosting to cdn.ncbi.nlm.nih.gov/pmc/blobs/{hash}/{pmcid}/{hash}/{file}.
        These hash-based paths cannot be derived from the JATS XML href alone — they require a
        single HTTP fetch of the article HTML page.  Returns a list of candidate CDN URLs
        that match the figure filename, or an empty list if resolution fails.
        """
        primary_url = figure.get("url") or ""
        # Extract the base filename from the primary URL (e.g. "nihms393293f1.jpg", "gr1_lrg.jpg")
        filename = primary_url.rstrip("/").split("/")[-1] if primary_url else ""
        if not filename:
            return []

        # Derive article page URL: strip trailing filename component to get article base
        # e.g. "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3465532/nihms393293f1.jpg"
        #   → "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3465532/"
        # Then map to pmc.ncbi.nlm.nih.gov (the HTML reader endpoint).
        article_base = primary_url[:primary_url.rfind("/") + 1] if "/" in primary_url else ""
        if not article_base:
            return []
        article_page = article_base.replace(
            "www.ncbi.nlm.nih.gov/pmc/articles/",
            "pmc.ncbi.nlm.nih.gov/articles/",
        )

        cdn_cache = getattr(self, "_pmc_cdn_url_cache", None)
        if cdn_cache is None:
            cdn_cache = {}
            setattr(self, "_pmc_cdn_url_cache", cdn_cache)

        try:
            if article_page in cdn_cache:
                all_cdn = cdn_cache[article_page]
            else:
                resp = self._figure_http_get(
                    article_page,
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0 (ResearchShop Figure Fetch)"},
                )
                if resp.status_code != 200:
                    return []
                cdn_pattern = re.compile(
                    r'https://cdn\.ncbi\.nlm\.nih\.gov/pmc/blobs/[^"\'>\s]+'
                )
                all_cdn = cdn_pattern.findall(resp.text)
                cdn_cache[article_page] = all_cdn

            # Extract all cdn.ncbi.nlm.nih.gov/pmc/blobs URLs whose filename matches
            stem = re.escape(re.sub(r'\.[^.]+$', '', filename))  # strip extension for fuzzy match
            # Prefer exact filename match, then stem match
            exact = [u for u in all_cdn if u.endswith("/" + filename)]
            if exact:
                return exact
            stem_matches = [u for u in all_cdn if re.search(r'/' + stem + r'[^/]*$', u)]
            return stem_matches
        except Exception:
            return []

    def _download_figure_url(
        self,
        url: str,
        *,
        max_bytes: int,
        timeout: int,
        headers: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """Download one image URL with type and size guards."""
        try:
            response = self._figure_http_get(
                url, timeout=timeout, stream=True, allow_redirects=True, headers=headers
            )
            if response.status_code != 200:
                return None

            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_bytes:
                return None

            mime_type = (
                (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            )
            if not mime_type.startswith("image/"):
                return None

            chunks: List[bytes] = []
            total = 0
            too_large = False
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    too_large = True
                    break
                chunks.append(chunk)

            if too_large:
                return None

            payload = b"".join(chunks)
            if not payload:
                return None

            return {"bytes": payload, "mime_type": mime_type, "url": url}
        except Exception:
            return None

    def _validate_figure_download(self, figure: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return downloadable figure bytes and the resolved URL, if available."""
        candidates = list(figure.get("url_candidates") or [])
        primary_url = figure.get("url")
        if primary_url and primary_url not in candidates:
            candidates.insert(0, primary_url)
        if not candidates:
            return None

        max_bytes = max(getattr(config, "FIGURE_IMAGE_MAX_BYTES", 5 * 1024 * 1024), 100000)
        timeout = max(getattr(config, "REQUEST_TIMEOUT", 30), 10)
        headers = {
            "User-Agent": "Mozilla/5.0 (ResearchShop Figure Fetch)",
            "Accept": "image/*,*/*;q=0.8",
        }

        # Phase 1: try pre-built candidate URLs
        for url in candidates:
            result = self._download_figure_url(
                url, max_bytes=max_bytes, timeout=timeout, headers=headers
            )
            if result:
                return result

        # Phase 2: CDN URL resolution fallback — fetch article HTML and extract blob URLs
        cdn_candidates = self._resolve_pmc_cdn_url(figure)
        if cdn_candidates:
            logging.debug(
                f"Figure fetch: primary candidates failed; trying {len(cdn_candidates)} CDN URL(s)"
            )
        for url in cdn_candidates:
            result = self._download_figure_url(
                url, max_bytes=max_bytes, timeout=timeout, headers=headers
            )
            if result:
                logging.debug(f"Figure fetch: CDN fallback succeeded for {url}")
                return result

        return None

    def _resolve_figure_download_url(self, figure: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Probe a figure and return URL/mime/size metadata without exposing bytes."""
        downloaded = self._validate_figure_download(figure)
        if not downloaded:
            return None
        return {
            "url": downloaded["url"],
            "mime_type": downloaded["mime_type"],
            "bytes": len(downloaded["bytes"]),
        }

    def _fetch_figure_image(self, figure: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Download a figure image from candidate URLs with size and type safeguards.

        Falls back to CDN URL resolution if all pre-built candidates return non-200.
        PMC migrated figure hosting to cdn.ncbi.nlm.nih.gov/pmc/blobs/... which requires
        an HTML page scrape to resolve the hash-based path components.
        """
        return self._validate_figure_download(figure)

    def extract_gene_names_from_figures(self) -> List[Dict[str, str]]:
        """
        Use Gemini multimodal analysis to discover gene/variant mentions from figure images.
        """
        if not getattr(config, "ENABLE_FIGURE_ANALYSIS", True):
            return []
        if not self.figure_inputs:
            return []

        from google.genai import types  # type: ignore

        from .gemini_client import FigureDiscoveryResponse

        model_name = config.GEMINI_CONFIG["gene_extraction_model"]
        max_figures = max(getattr(config, "FIGURE_MAX_IMAGES_PER_PAPER", 3), 0)
        if max_figures == 0:
            return []

        generate_content_config = types.GenerateContentConfig(
            temperature=config.GEMINI_CONFIG["temperature"],
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            response_mime_type="application/json",
            response_schema=FigureDiscoveryResponse,
        )

        discovered: List[Dict[str, str]] = []
        _fig_inter_call_delay = max(
            int(getattr(config, "FIGURE_INTER_CALL_DELAY_SECONDS", 4)), 0
        )
        for idx, figure in enumerate(self.figure_inputs[:max_figures], start=1):
            if idx > 1 and _fig_inter_call_delay > 0:
                # Small mandatory gap between figure vision calls: prevents back-to-back
                # calls from immediately re-saturating the per-minute sliding rate window.
                time.sleep(_fig_inter_call_delay)
            downloaded = self._fetch_figure_image(figure)
            if not downloaded:
                logging.debug(f"Figure analysis skipped for figure {idx}: could not download image")
                continue

            image_part = self._build_gemini_image_part(
                types, downloaded["bytes"], downloaded["mime_type"]
            )
            if image_part is None:
                logging.debug(
                    f"Figure analysis skipped for figure {idx}: unsupported image part creation"
                )
                continue

            label = (figure.get("label") or "").strip()
            caption = (figure.get("caption") or "").strip()
            prompt = (
                _FIGURE_ANALYSIS_INSTRUCTION
                + f"\n\nFigure label: {label or 'N/A'}"
                + f"\nFigure caption: {caption or 'N/A'}"
            )

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=prompt),
                        image_part,
                    ],
                )
            ]

            fig_max_retries = max(1, int(getattr(config, "GEMINI_OPTIONAL_MAX_RETRIES", 1)))
            fig_success = False
            for fig_attempt in range(fig_max_retries):
                try:
                    response_json = self._generate_content_json(
                        model_name=model_name,
                        contents=contents,
                        generate_content_config=generate_content_config,
                        purpose=f"figure analysis {idx}",
                        optional=True,
                        reserved_required_calls=1,
                        response_model=FigureDiscoveryResponse,
                    )
                    if not response_json:
                        break

                    associations = self._associations_from_structured_response(
                        response_json,
                        f"figure analysis {idx}",
                        FigureDiscoveryResponse,
                    )
                    for assoc in associations:
                        if not isinstance(assoc, dict):
                            continue
                        gene = (assoc.get("gene") or "").strip()
                        variant = (assoc.get("variant") or "").strip()
                        if not gene:
                            continue
                        discovered.append({"gene": gene, "variant": variant})
                    fig_success = True
                    break
                except Exception as e:
                    should_retry, wait = self._should_retry_gemini_error(
                        e, fig_attempt, fig_max_retries
                    )
                    if should_retry:
                        logging.info(
                            f"Figure analysis rate limited for figure {idx} "
                            f"(attempt {fig_attempt + 1}/{fig_max_retries}): "
                            f"waiting {wait}s before retry"
                        )
                        time.sleep(wait)
                    else:
                        logging.warning(f"Figure analysis failed for figure {idx}: {e}")
                        break
            if not fig_success:
                continue

        # De-duplicate gene/variant pairs
        deduped: List[Dict[str, str]] = []
        seen = set()
        for assoc in discovered:
            gene_norm = assoc["gene"].strip().upper()
            variant_norm = (assoc.get("variant") or "").strip()
            if variant_norm.upper() in {"N/A", "NA", "NONE"}:
                variant_norm = ""
            key = (gene_norm, variant_norm.upper())
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"gene": assoc["gene"], "variant": variant_norm})

        if deduped:
            logging.info(f"Figure analysis discovered {len(deduped)} unique gene associations")
        return deduped
