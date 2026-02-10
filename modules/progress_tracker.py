# modules/progress_tracker.py

"""
Enhanced progress tracking and logging system for the pipeline.

Provides:
- Progress bars for all pipeline steps
- Timing statistics for each step
- Parallelization performance analysis
- Comprehensive logging with metrics
"""

import time
import logging
from typing import Dict, Optional, Callable
from tqdm import tqdm
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class StepTimer:
    """Track timing for a single pipeline step."""

    def __init__(self, step_name: str):
        self.step_name = step_name
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.elapsed: Optional[float] = None

    def start(self):
        self.start_time = time.time()
        logger.info(f"⏱️  Starting step: {self.step_name}")

    def stop(self):
        self.end_time = time.time()
        self.elapsed = self.end_time - self.start_time
        logger.info(f"✅ Completed step: {self.step_name} in {self.elapsed:.2f}s")

    @contextmanager
    def context(self):
        """Use as context manager for automatic timing."""
        self.start()
        try:
            yield self
        finally:
            self.stop()


class PipelineProgressTracker:
    """Track progress and timing across all pipeline steps."""

    def __init__(self, total_steps: int = 10):
        self.steps: Dict[str, StepTimer] = {}
        self.parallelization_stats: Dict[str, Dict] = {}
        self.start_time = time.time()
        self.current_step = 0
        self.total_steps = total_steps

    def start_step(self, step_name: str, description: str = "") -> StepTimer:
        """Start tracking a new step."""
        timer = StepTimer(step_name)
        timer.start()
        self.steps[step_name] = timer
        self.current_step += 1

        progress_pct = int((self.current_step / self.total_steps) * 100)
        if description:
            logger.info(f"📊 [{progress_pct}%] {step_name}: {description}")
        else:
            logger.info(f"📊 [{progress_pct}%] {step_name}")

        return timer

    def track_parallelization(
        self,
        step_name: str,
        total_items: int,
        num_workers: int,
        elapsed_time: float,
        successful: int,
        failed: int,
    ):
        """Track parallelization performance for a step."""
        if total_items == 0:
            return

        # Calculate theoretical sequential time (estimate)
        avg_time_per_item = elapsed_time / total_items if total_items > 0 else 0
        estimated_sequential_time = avg_time_per_item * total_items

        # Calculate speedup
        speedup = estimated_sequential_time / elapsed_time if elapsed_time > 0 else 1.0

        # Calculate efficiency (speedup / num_workers)
        efficiency = speedup / num_workers if num_workers > 0 else 0.0

        # Calculate throughput
        throughput = total_items / elapsed_time if elapsed_time > 0 else 0.0

        self.parallelization_stats[step_name] = {
            "total_items": total_items,
            "num_workers": num_workers,
            "elapsed_time": elapsed_time,
            "successful": successful,
            "failed": failed,
            "success_rate": (
                (successful / total_items * 100) if total_items > 0 else 0.0
            ),
            "estimated_sequential_time": estimated_sequential_time,
            "speedup": speedup,
            "efficiency": efficiency,
            "throughput_items_per_second": throughput,
        }

        logger.info(f"🚀 Parallelization stats for {step_name}:")
        logger.info(f"   Workers: {num_workers}, Items: {total_items}")
        logger.info(
            f"   Elapsed: {elapsed_time:.2f}s, Success: {successful}, Failed: {failed}"
        )
        logger.info(f"   Speedup: {speedup:.2f}x, Efficiency: {efficiency:.1%}")
        logger.info(f"   Throughput: {throughput:.2f} items/s")

    def get_summary(self) -> Dict:
        """Get summary of all timing and performance metrics."""
        total_elapsed = time.time() - self.start_time

        summary = {
            "total_pipeline_time": total_elapsed,
            "step_timings": {
                name: timer.elapsed
                for name, timer in self.steps.items()
                if timer.elapsed is not None
            },
            "parallelization_stats": self.parallelization_stats,
        }

        return summary

    def log_summary(self):
        """Log comprehensive summary of pipeline performance."""
        summary = self.get_summary()

        logger.info("=" * 80)
        logger.info("📈 PIPELINE PERFORMANCE SUMMARY")
        logger.info("=" * 80)
        logger.info(f"⏱️  Total pipeline time: {summary['total_pipeline_time']:.2f}s")
        logger.info("")
        logger.info("Step timings:")
        for step_name, elapsed in summary["step_timings"].items():
            percentage = (
                (elapsed / summary["total_pipeline_time"] * 100)
                if summary["total_pipeline_time"] > 0
                else 0
            )
            logger.info(f"  • {step_name}: {elapsed:.2f}s ({percentage:.1f}%)")
        logger.info("")

        if summary["parallelization_stats"]:
            logger.info("🚀 Parallelization Analysis:")
            for step_name, stats in summary["parallelization_stats"].items():
                logger.info(f"  {step_name}:")
                logger.info(
                    f"    • Speedup: {stats['speedup']:.2f}x (theoretical max: {stats['num_workers']}x)"
                )
                logger.info(f"    • Efficiency: {stats['efficiency']:.1%}")
                logger.info(
                    f"    • Throughput: {stats['throughput_items_per_second']:.2f} items/s"
                )
                logger.info(f"    • Success rate: {stats['success_rate']:.1f}%")
        logger.info("=" * 80)


# Global tracker instance
_tracker: Optional[PipelineProgressTracker] = None


def get_tracker() -> PipelineProgressTracker:
    """Get or create the global progress tracker."""
    global _tracker
    if _tracker is None:
        _tracker = PipelineProgressTracker()
    return _tracker


def reset_tracker():
    """Reset the global tracker (useful for testing)."""
    global _tracker
    _tracker = None
