/**
 * PubMed Service — search PubMed via NCBI E-utilities using native fetch().
 */

import { logger } from "./logger-service.js";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PubMedArticle {
  pmid: string;
  title: string;
  authors: string[];
  journal: string;
  year: string;
  abstract: string;
}

interface ESearchResult {
  esearchresult: {
    count: string;
    idlist: string[];
    querytranslation?: string;
  };
}

interface ESummaryResult {
  result: Record<
    string,
    {
      uid: string;
      title: string;
      sortfirstauthor?: string;
      authors?: { name: string }[];
      source: string;
      pubdate: string;
    }
  >;
}

interface EFetchXMLParsed {
  pmid: string;
  title: string;
  authors: string[];
  journal: string;
  year: string;
  abstract: string;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils";
const BATCH_SIZE = 50;

function buildParams(
  extra: Record<string, string>,
  email?: string,
  apiKey?: string,
): URLSearchParams {
  const params = new URLSearchParams({
    db: "pubmed",
    retmode: "json",
    ...extra,
  });
  if (email) params.set("email", email);
  if (apiKey) params.set("api_key", apiKey);
  return params;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function countResults(
  query: string,
  email?: string,
  apiKey?: string,
): Promise<number> {
  const params = buildParams(
    { term: query, rettype: "count" },
    email,
    apiKey,
  );
  const url = `${BASE_URL}/esearch.fcgi?${params.toString()}`;

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`PubMed esearch error: ${res.status}`);
  }
  const data = (await res.json()) as ESearchResult;
  return parseInt(data.esearchresult.count, 10) || 0;
}

export async function searchPubMed(
  query: string,
  maxResults: number,
  email?: string,
  apiKey?: string,
): Promise<PubMedArticle[]> {
  logger.info(
    `PubMed search: "${query}" (max ${maxResults})`,
    "PubMedService",
  );

  // Step 1: esearch to get PMIDs
  const searchParams = buildParams(
    { term: query, retmax: String(maxResults), usehistory: "y" },
    email,
    apiKey,
  );
  const searchUrl = `${BASE_URL}/esearch.fcgi?${searchParams.toString()}`;

  const searchRes = await fetch(searchUrl);
  if (!searchRes.ok) {
    throw new Error(`PubMed esearch error: ${searchRes.status}`);
  }
  const searchData = (await searchRes.json()) as ESearchResult;
  const pmids = searchData.esearchresult.idlist;

  if (pmids.length === 0) {
    logger.info("PubMed search returned 0 results", "PubMedService");
    return [];
  }

  logger.info(`PubMed search found ${pmids.length} PMIDs`, "PubMedService");

  // Step 2: Fetch details in batches
  const articles: PubMedArticle[] = [];

  for (let i = 0; i < pmids.length; i += BATCH_SIZE) {
    const batch = pmids.slice(i, i + BATCH_SIZE);
    const batchArticles = await fetchSummaries(batch, email, apiKey);
    articles.push(...batchArticles);
  }

  return articles;
}

export async function resolvePmids(
  pmids: string[],
  email?: string,
  apiKey?: string,
): Promise<PubMedArticle[]> {
  if (pmids.length === 0) return [];

  const articles: PubMedArticle[] = [];
  for (let i = 0; i < pmids.length; i += BATCH_SIZE) {
    const batch = pmids.slice(i, i + BATCH_SIZE);
    const batchArticles = await fetchSummaries(batch, email, apiKey);
    articles.push(...batchArticles);
  }
  return articles;
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

async function fetchSummaries(
  pmids: string[],
  email?: string,
  apiKey?: string,
): Promise<PubMedArticle[]> {
  const params = buildParams(
    { id: pmids.join(","), rettype: "abstract" },
    email,
    apiKey,
  );
  const url = `${BASE_URL}/esummary.fcgi?${params.toString()}`;

  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`PubMed esummary error: ${res.status}`);
  }

  const data = (await res.json()) as ESummaryResult;
  const articles: PubMedArticle[] = [];

  for (const pmid of pmids) {
    const record = data.result?.[pmid];
    if (!record) continue;

    const authors =
      record.authors?.map((a) => a.name) ?? [];

    // Extract year from pubdate (e.g. "2023 Jan 15" -> "2023")
    const yearMatch = record.pubdate?.match(/\d{4}/);
    const year = yearMatch ? yearMatch[0] : "";

    articles.push({
      pmid: record.uid,
      title: record.title ?? "",
      authors,
      journal: record.source ?? "",
      year,
      abstract: "", // esummary doesn't return abstracts; use efetch if needed
    });
  }

  return articles;
}

/**
 * Fetch full abstracts for a batch of PMIDs using efetch (XML).
 * This is more expensive but returns abstract text.
 */
export async function fetchAbstracts(
  pmids: string[],
  email?: string,
  apiKey?: string,
): Promise<EFetchXMLParsed[]> {
  if (pmids.length === 0) return [];

  const params = new URLSearchParams({
    db: "pubmed",
    retmode: "xml",
    rettype: "abstract",
    id: pmids.join(","),
  });
  if (email) params.set("email", email);
  if (apiKey) params.set("api_key", apiKey);

  const url = `${BASE_URL}/efetch.fcgi?${params.toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`PubMed efetch error: ${res.status}`);
  }

  const xml = await res.text();
  return parseEFetchXML(xml);
}

/**
 * Minimal XML parser for efetch PubmedArticle results.
 * Avoids external XML dependencies by using regex extraction.
 */
function parseEFetchXML(xml: string): EFetchXMLParsed[] {
  const articles: EFetchXMLParsed[] = [];
  const articleBlocks = xml.split("<PubmedArticle>");

  for (let i = 1; i < articleBlocks.length; i++) {
    const block = articleBlocks[i];

    const pmidMatch = block.match(/<PMID[^>]*>(\d+)<\/PMID>/);
    const titleMatch = block.match(
      /<ArticleTitle>([\s\S]*?)<\/ArticleTitle>/,
    );
    const journalMatch = block.match(/<Title>([\s\S]*?)<\/Title>/);
    const yearMatch = block.match(/<PubDate>[\s\S]*?<Year>(\d{4})<\/Year>/);
    const abstractMatch = block.match(
      /<AbstractText[^>]*>([\s\S]*?)<\/AbstractText>/g,
    );

    const authorMatches = [
      ...block.matchAll(
        /<Author[\s\S]*?<LastName>([\s\S]*?)<\/LastName>[\s\S]*?<ForeName>([\s\S]*?)<\/ForeName>/g,
      ),
    ];
    const authors = authorMatches.map(
      (m) => `${stripTags(m[2])} ${stripTags(m[1])}`,
    );

    const abstractParts = abstractMatch
      ? abstractMatch.map((a) =>
          stripTags(a.replace(/<\/?AbstractText[^>]*>/g, "")),
        )
      : [];

    articles.push({
      pmid: pmidMatch?.[1] ?? "",
      title: stripTags(titleMatch?.[1] ?? ""),
      authors,
      journal: stripTags(journalMatch?.[1] ?? ""),
      year: yearMatch?.[1] ?? "",
      abstract: abstractParts.join(" "),
    });
  }

  return articles;
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, "").trim();
}
