from typing import Set

from tracr.rasp import rasp

from circuits_benchmark.benchmark import vocabs
from circuits_benchmark.benchmark.tracr_benchmark_case import TracrBenchmarkCase


class Case23(TracrBenchmarkCase):
    def get_program(self) -> rasp.SOp:
        return make_palindrome_word_spotter(rasp.tokens)

    def get_task_description(self) -> str:
        return "Returns palindrome words in a sequence."

    def get_vocab(self) -> Set:
        return vocabs.get_words_vocab().union({"racecar", "noon"})


def make_palindrome_word_spotter(sop: rasp.SOp) -> rasp.SOp:
    """
    Spots palindrome words in a sequence.

    Example usage:
      palindrome_spotter = make_palindrome_word_spotter(rasp.tokens)
      palindrome_spotter(["racecar", "hello", "noon"])
      >> ["racecar", None, "noon"]
    """
    is_palindrome = rasp.Map(lambda x: x if x == x[::-1] else None, sop)
    return is_palindrome
