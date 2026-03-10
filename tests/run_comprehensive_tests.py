"""Comprehensive test suite for zendesk analytics bot."""

import requests
import json
import time
from typing import Dict, List, Any
from datetime import datetime
from collections import defaultdict


class TestRunner:
    """Run comprehensive tests on the analytics bot."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.results = []
        self.stats = defaultdict(int)

    def test_query(self, question: str, category: str) -> Dict[str, Any]:
        """Test a single query and record results."""
        print(f"  Testing: {question}")

        start = time.time()
        try:
            response = requests.post(
                f"{self.base_url}/chat",
                json={"question": question},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            elapsed = time.time() - start

            if response.status_code == 200:
                result = response.json()

                # Analyze result quality
                answer = result.get("answer", "")
                metadata = result.get("metadata", {})

                # Determine success criteria
                success = self._evaluate_success(answer, metadata, category)

                return {
                    "question": question,
                    "category": category,
                    "success": success,
                    "time_ms": int(elapsed * 1000),
                    "answer_preview": answer[:150],
                    "count": metadata.get("count"),
                    "organization": metadata.get("organization"),
                    "query_type": result.get("query_type"),
                    "evidence_count": len(result.get("evidence", [])),
                    "status_code": 200
                }
            else:
                return {
                    "question": question,
                    "category": category,
                    "success": False,
                    "time_ms": int(elapsed * 1000),
                    "error": f"HTTP {response.status_code}",
                    "status_code": response.status_code
                }

        except Exception as e:
            elapsed = time.time() - start
            return {
                "question": question,
                "category": category,
                "success": False,
                "time_ms": int(elapsed * 1000),
                "error": str(e),
                "status_code": 0
            }

    def _evaluate_success(self, answer: str, metadata: Dict, category: str) -> bool:
        """Evaluate if query was successful based on category."""
        answer_lower = answer.lower()

        # Empty or error responses
        if "couldn't find" in answer_lower or "no relevant" in answer_lower:
            return False

        if not answer or len(answer) < 10:
            return False

        # Category-specific checks
        if category == "count_queries":
            # Should have a number
            count = metadata.get("count")
            return count is not None and count >= 0

        elif category == "organization_queries":
            # Should have tickets listed
            return "ticket" in answer_lower or "#" in answer

        elif category in ["priority_queries", "status_queries"]:
            # Should show tickets
            return "#" in answer or "ticket" in answer_lower

        elif category == "semantic_search_queries":
            # Should have found something or explain why not
            return len(answer) > 50

        elif category == "aggregate_queries":
            # Should show multiple organizations
            return len(answer) > 100

        elif category == "time_based_queries":
            # Should mention time period
            return len(answer) > 50

        elif category == "combined_queries":
            # Should have specific results
            return len(answer) > 50

        return True

    def run_tests(self, test_queries: Dict[str, List[str]]):
        """Run all test queries."""
        print("🧪 Starting Comprehensive Test Suite")
        print("=" * 80)

        total_queries = sum(len(queries) for queries in test_queries.values())
        print(f"\nTotal Queries: {total_queries}\n")

        for category, queries in test_queries.items():
            print(f"\n📂 Testing: {category.replace('_', ' ').title()}")
            print("-" * 80)

            for query in queries:
                result = self.test_query(query, category)
                self.results.append(result)

                # Update stats
                if result["success"]:
                    self.stats["success"] += 1
                    status = "✓"
                else:
                    self.stats["failed"] += 1
                    status = "✗"

                self.stats["total"] += 1
                self.stats[f"{category}_total"] += 1
                if result["success"]:
                    self.stats[f"{category}_success"] += 1

                # Print brief result
                time_str = f"{result['time_ms']}ms"
                print(f"    {status} [{time_str}] {result.get('error', 'OK')}")

        print("\n" + "=" * 80)

    def print_summary(self):
        """Print test summary."""
        print("\n📊 Test Summary")
        print("=" * 80)

        total = self.stats["total"]
        success = self.stats["success"]
        failed = self.stats["failed"]
        success_rate = (success / total * 100) if total > 0 else 0

        print(f"\nOverall Results:")
        print(f"  Total Queries: {total}")
        print(f"  Successful: {success} ({success_rate:.1f}%)")
        print(f"  Failed: {failed} ({100 - success_rate:.1f}%)")

        # Average time
        times = [r["time_ms"] for r in self.results if r.get("time_ms")]
        avg_time = sum(times) / len(times) if times else 0
        print(f"  Average Time: {int(avg_time)}ms")

        # Category breakdown
        print("\nCategory Breakdown:")
        categories = set(r["category"] for r in self.results)

        for category in sorted(categories):
            cat_total = self.stats[f"{category}_total"]
            cat_success = self.stats.get(f"{category}_success", 0)
            cat_rate = (cat_success / cat_total * 100) if cat_total > 0 else 0
            print(f"  {category.replace('_', ' ').title():30} {cat_success}/{cat_total} ({cat_rate:.0f}%)")

        # Common failures
        print("\nTop Failures:")
        failures = [r for r in self.results if not r["success"]]
        failure_reasons = defaultdict(int)

        for f in failures:
            reason = f.get("error", "No results found")
            if "couldn't find" in f.get("answer_preview", "").lower():
                reason = "No relevant tickets found"
            failure_reasons[reason] += 1

        for reason, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {reason}: {count} times")

    def save_results(self, filename: str = "test_results.json"):
        """Save detailed results to file."""
        output = {
            "timestamp": datetime.now().isoformat(),
            "stats": dict(self.stats),
            "results": self.results
        }

        with open(filename, "w") as f:
            json.dump(output, f, indent=2)

        print(f"\n💾 Detailed results saved to: {filename}")

    def generate_improvement_report(self) -> List[str]:
        """Generate list of improvements needed."""
        improvements = []

        # Analyze failures by category
        for category in set(r["category"] for r in self.results):
            cat_results = [r for r in self.results if r["category"] == category]
            cat_failures = [r for r in cat_results if not r["success"]]

            if len(cat_failures) > len(cat_results) * 0.3:  # >30% failure
                failure_rate = len(cat_failures) / len(cat_results) * 100
                improvements.append(
                    f"HIGH PRIORITY: Fix {category} (failure rate: {failure_rate:.0f}%)"
                )

        # Check for slow queries
        slow_queries = [r for r in self.results if r.get("time_ms", 0) > 5000]
        if slow_queries:
            improvements.append(
                f"PERFORMANCE: Optimize {len(slow_queries)} slow queries (>5s)"
            )

        # Check for specific issues
        no_results = len([r for r in self.results if "couldn't find" in r.get("answer_preview", "").lower()])
        if no_results > 10:
            improvements.append(
                f"ACCURACY: Improve search - {no_results} queries returned no results"
            )

        return improvements


def main():
    """Run comprehensive tests."""
    # Load test queries
    with open("tests/test_queries.json", "r") as f:
        test_queries = json.load(f)

    # Run tests
    runner = TestRunner()
    runner.run_tests(test_queries)

    # Print summary
    runner.print_summary()

    # Save results
    runner.save_results("tests/test_results.json")

    # Generate improvement report
    print("\n🔧 Improvement Recommendations")
    print("=" * 80)
    improvements = runner.generate_improvement_report()

    if improvements:
        for i, improvement in enumerate(improvements, 1):
            print(f"{i}. {improvement}")
    else:
        print("✓ System performing well! No critical improvements needed.")

    print("\n" + "=" * 80)
    print("✅ Testing complete!")


if __name__ == "__main__":
    main()
