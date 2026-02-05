"""
Similarity matching module for trademark monitoring.
Implements multiple algorithms to detect potentially confusing marks.
"""

import re
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class SimilarityResult:
    """Result of similarity analysis."""
    score: float  # 0-100 scale
    is_match: bool
    reasons: Dict[str, Any]
    matched_trademark: str


class TrademarkSimilarity:
    """
    Analyzes trademark similarity using multiple methods:
    - Exact match
    - Prefix/suffix matching
    - Contains matching
    - Levenshtein (edit) distance
    - Phonetic similarity (Soundex, Metaphone)
    - Pattern matching
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.min_score = self.config.get('min_score', 65)
        self.weights = self.config.get('weights', {
            'exact_match': 100,
            'starts_with': 85,
            'contains': 70,
            'phonetic': 75,
            'levenshtein': 1.0
        })
        self.watch_patterns = self.config.get('watch_patterns', [])

        # Our trademarks to compare against
        self.our_marks = ['TOPO', 'TOPOLOGY']

    def set_our_marks(self, marks: List[str]):
        """Set the list of our trademarks to monitor."""
        self.our_marks = [m.upper() for m in marks]

    def analyze(self, candidate_mark: str) -> List[SimilarityResult]:
        """
        Analyze a candidate mark against all our trademarks.
        Returns a list of SimilarityResult for each match above threshold.
        """
        if not candidate_mark:
            return []

        candidate = self._normalize(candidate_mark)
        results = []

        for our_mark in self.our_marks:
            our_normalized = self._normalize(our_mark)
            result = self._compare_marks(candidate, our_normalized, our_mark)
            if result.is_match:
                results.append(result)

        return results

    def _normalize(self, mark: str) -> str:
        """Normalize a trademark for comparison."""
        if not mark:
            return ""
        # Convert to uppercase
        normalized = mark.upper()
        # Remove common design elements notations
        normalized = re.sub(r'\(.*?\)', '', normalized)
        # Remove special characters but keep spaces
        normalized = re.sub(r'[^\w\s]', '', normalized)
        # Normalize whitespace
        normalized = ' '.join(normalized.split())
        return normalized.strip()

    def _compare_marks(self, candidate: str, our_mark: str, original_our_mark: str) -> SimilarityResult:
        """Compare a candidate mark against one of our marks."""
        reasons = {}
        scores = []

        # 1. Exact match
        if candidate == our_mark:
            return SimilarityResult(
                score=100,
                is_match=True,
                reasons={'exact_match': True},
                matched_trademark=original_our_mark
            )

        # 2. Starts with our mark
        if candidate.startswith(our_mark):
            score = self.weights['starts_with']
            reasons['starts_with'] = f"Starts with '{our_mark}'"
            scores.append(score)

        # 3. Ends with our mark
        if candidate.endswith(our_mark):
            score = self.weights['starts_with'] - 5  # Slightly lower than starts_with
            reasons['ends_with'] = f"Ends with '{our_mark}'"
            scores.append(score)

        # 4. Contains our mark
        if our_mark in candidate and 'starts_with' not in reasons and 'ends_with' not in reasons:
            score = self.weights['contains']
            reasons['contains'] = f"Contains '{our_mark}'"
            scores.append(score)

        # 5. Levenshtein distance
        lev_score = self._levenshtein_similarity(candidate, our_mark)
        if lev_score >= 60:  # Only count if reasonably similar
            reasons['levenshtein'] = f"Edit distance similarity: {lev_score:.1f}%"
            scores.append(lev_score * self.weights['levenshtein'])

        # 6. Phonetic similarity
        phonetic_score = self._phonetic_similarity(candidate, our_mark)
        if phonetic_score >= 50:
            reasons['phonetic'] = f"Phonetic similarity: {phonetic_score:.1f}%"
            scores.append(phonetic_score * (self.weights['phonetic'] / 100))

        # 7. Pattern matching
        for pattern in self.watch_patterns:
            if re.search(pattern, candidate, re.IGNORECASE):
                reasons['pattern_match'] = f"Matches watch pattern: {pattern}"
                scores.append(75)
                break

        # 8. Common variations check
        variation_score = self._check_variations(candidate, our_mark)
        if variation_score > 0:
            reasons['variation'] = f"Common variation detected"
            scores.append(variation_score)

        # Calculate final score (weighted average with boost for multiple signals)
        if not scores:
            final_score = 0
        else:
            # Base score is the max of individual scores
            final_score = max(scores)
            # Boost if multiple signals detected
            if len(scores) > 1:
                final_score = min(100, final_score + (len(scores) - 1) * 5)

        return SimilarityResult(
            score=final_score,
            is_match=final_score >= self.min_score,
            reasons=reasons,
            matched_trademark=original_our_mark
        )

    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate similarity based on Levenshtein distance.
        Returns percentage similarity (0-100).
        """
        if not s1 or not s2:
            return 0

        # Remove spaces for comparison
        s1 = s1.replace(' ', '')
        s2 = s2.replace(' ', '')

        if s1 == s2:
            return 100

        len1, len2 = len(s1), len(s2)
        max_len = max(len1, len2)

        # Create distance matrix
        dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        for i in range(len1 + 1):
            dp[i][0] = i
        for j in range(len2 + 1):
            dp[0][j] = j

        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i-1] == s2[j-1] else 1
                dp[i][j] = min(
                    dp[i-1][j] + 1,      # deletion
                    dp[i][j-1] + 1,      # insertion
                    dp[i-1][j-1] + cost  # substitution
                )

        distance = dp[len1][len2]
        similarity = ((max_len - distance) / max_len) * 100
        return similarity

    def _phonetic_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate phonetic similarity using Soundex.
        Returns percentage similarity (0-100).
        """
        soundex1 = self._soundex(s1)
        soundex2 = self._soundex(s2)

        if soundex1 == soundex2:
            return 100

        # Compare soundex codes character by character
        matches = sum(1 for a, b in zip(soundex1, soundex2) if a == b)
        similarity = (matches / max(len(soundex1), len(soundex2))) * 100

        # Also check Double Metaphone
        meta1 = self._metaphone(s1)
        meta2 = self._metaphone(s2)

        if meta1 == meta2:
            return 100

        # Return the higher of the two phonetic scores
        meta_matches = sum(1 for a, b in zip(meta1, meta2) if a == b)
        meta_similarity = (meta_matches / max(len(meta1), len(meta2), 1)) * 100

        return max(similarity, meta_similarity)

    def _soundex(self, s: str) -> str:
        """Generate Soundex code for a string."""
        if not s:
            return ""

        s = s.upper().replace(' ', '')
        if not s:
            return ""

        # Soundex mapping
        mapping = {
            'B': '1', 'F': '1', 'P': '1', 'V': '1',
            'C': '2', 'G': '2', 'J': '2', 'K': '2', 'Q': '2', 'S': '2', 'X': '2', 'Z': '2',
            'D': '3', 'T': '3',
            'L': '4',
            'M': '5', 'N': '5',
            'R': '6'
        }

        # Keep first letter
        result = s[0]

        # Encode rest
        prev_code = mapping.get(s[0], '0')
        for char in s[1:]:
            code = mapping.get(char, '0')
            if code != '0' and code != prev_code:
                result += code
            prev_code = code if code != '0' else prev_code

        # Pad with zeros or truncate
        result = (result + '0000')[:4]
        return result

    def _metaphone(self, s: str) -> str:
        """Simplified Metaphone implementation."""
        if not s:
            return ""

        s = s.upper().replace(' ', '')
        if not s:
            return ""

        # Simplified metaphone rules
        result = []
        i = 0
        while i < len(s):
            c = s[i]

            # Skip duplicates
            if i > 0 and c == s[i-1]:
                i += 1
                continue

            # Vowels only at start
            if c in 'AEIOU':
                if i == 0:
                    result.append(c)
            elif c in 'BFPV':
                result.append('P')
            elif c in 'CGJKQSXZ':
                result.append('K')
            elif c in 'DT':
                result.append('T')
            elif c == 'L':
                result.append('L')
            elif c in 'MN':
                result.append('N')
            elif c == 'R':
                result.append('R')
            elif c == 'W':
                if i < len(s) - 1 and s[i+1] in 'AEIOU':
                    result.append('W')
            elif c == 'Y':
                if i < len(s) - 1 and s[i+1] in 'AEIOU':
                    result.append('Y')

            i += 1

        return ''.join(result)[:6]

    def _check_variations(self, candidate: str, our_mark: str) -> float:
        """Check for common trademark variations."""
        candidate_clean = candidate.replace(' ', '')
        our_clean = our_mark.replace(' ', '')

        variations = []

        # Common prefixes
        prefixes = ['E', 'I', 'MY', 'THE', 'GO', 'PRO', 'SUPER', 'ULTRA', 'MEGA', 'SMART']
        for prefix in prefixes:
            variations.append(prefix + our_clean)

        # Common suffixes
        suffixes = ['APP', 'APPS', 'LY', 'IO', 'HQ', 'HUB', 'PLUS', 'PRO', 'NOW', 'GO', 'NET', 'TECH']
        for suffix in suffixes:
            variations.append(our_clean + suffix)

        # Check if candidate matches any variation
        for var in variations:
            if candidate_clean == var:
                return 80
            elif candidate_clean.startswith(var) or candidate_clean.endswith(var):
                return 70

        return 0

    def get_class_relevance(self, classes: List[int], goods_services: str = None,
                           target_classes: List[int] = None,
                           priority_keywords: List[str] = None) -> Dict[str, Any]:
        """
        Evaluate how relevant a trademark's classes and goods/services are.
        Returns relevance score and reasons.
        """
        if target_classes is None:
            target_classes = [9, 42]  # Our classes

        if priority_keywords is None:
            priority_keywords = [
                'software', 'mobile', 'application', 'app', 'social',
                'networking', 'platform', 'downloadable', 'online', 'saas',
                'cloud', 'internet', 'computer', 'digital'
            ]

        relevance = {'score': 0, 'reasons': [], 'class_match': False, 'keyword_match': False}

        # Check class overlap
        class_overlap = set(classes or []) & set(target_classes)
        if class_overlap:
            relevance['class_match'] = True
            relevance['score'] += 50
            relevance['reasons'].append(f"Matching classes: {list(class_overlap)}")

        # Check goods/services keywords
        if goods_services:
            gs_lower = goods_services.lower()
            matched_keywords = [kw for kw in priority_keywords if kw in gs_lower]
            if matched_keywords:
                relevance['keyword_match'] = True
                relevance['score'] += min(50, len(matched_keywords) * 10)
                relevance['reasons'].append(f"Keywords found: {matched_keywords[:5]}")

        return relevance

    def full_analysis(self, filing: Dict[str, Any],
                     target_classes: List[int] = None,
                     priority_keywords: List[str] = None) -> Optional[Dict[str, Any]]:
        """
        Perform full similarity and relevance analysis on a filing.
        Returns analysis result if it's a potential conflict, None otherwise.
        """
        mark_text = filing.get('mark_text', '')
        classes = filing.get('classes', [])
        goods_services = filing.get('goods_services', '')

        # First check class relevance
        relevance = self.get_class_relevance(classes, goods_services, target_classes, priority_keywords)

        # Only proceed with similarity if class is relevant
        if not relevance['class_match']:
            return None

        # Check similarity
        similarity_results = self.analyze(mark_text)

        if not similarity_results:
            return None

        # Get best match
        best_match = max(similarity_results, key=lambda x: x.score)

        if not best_match.is_match:
            return None

        # Combine scores - weight similarity more heavily
        combined_score = (best_match.score * 0.7) + (relevance['score'] * 0.3)

        return {
            'serial_number': filing.get('serial_number'),
            'mark_text': mark_text,
            'matched_trademark': best_match.matched_trademark,
            'similarity_score': round(combined_score, 2),
            'similarity_reasons': {
                'mark_similarity': best_match.reasons,
                'class_relevance': relevance['reasons']
            },
            'classes': classes,
            'goods_services': goods_services,
            'applicant_name': filing.get('applicant_name'),
            'filing_date': filing.get('filing_date')
        }


# Convenience function for quick similarity check
def check_similarity(candidate: str, our_marks: List[str] = None,
                    min_score: float = 65) -> List[SimilarityResult]:
    """Quick similarity check without full class analysis."""
    analyzer = TrademarkSimilarity({'min_score': min_score})
    if our_marks:
        analyzer.set_our_marks(our_marks)
    return analyzer.analyze(candidate)


if __name__ == "__main__":
    # Test the similarity module
    analyzer = TrademarkSimilarity({
        'min_score': 60,
        'watch_patterns': [r'^TOPO', r'TOPO$', r'^TOPOLOGY', r'TOPOL']
    })

    test_marks = [
        "TOPO",
        "TOPOLOGY",
        "TOPOMAP",
        "TOPOLINK",
        "MYTOPO",
        "TOPOGRAPHY",
        "TOPOLOGIC",
        "TOPOSPHERE",
        "TOPOSOCIAL",
        "ETOPO",
        "RANDOM MARK",
        "APPLE",
        "SOFTTOP"
    ]

    print("Similarity Analysis Test Results")
    print("=" * 60)
    for mark in test_marks:
        results = analyzer.analyze(mark)
        if results:
            for r in results:
                print(f"\n{mark}:")
                print(f"  Matched: {r.matched_trademark}")
                print(f"  Score: {r.score:.1f}")
                print(f"  Reasons: {r.reasons}")
        else:
            print(f"\n{mark}: No match")
