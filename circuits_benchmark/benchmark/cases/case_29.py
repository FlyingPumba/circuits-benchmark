from typing import Set

from tracr.rasp import rasp

from circuits_benchmark.benchmark import vocabs
from circuits_benchmark.benchmark.tracr_benchmark_case import TracrBenchmarkCase


class Case29(TracrBenchmarkCase):
    def get_program(self) -> rasp.SOp:
        return make_token_abbreviation(rasp.tokens)

    def get_task_description(self) -> str:
        return "Creates abbreviations for each token in the sequence."

    def get_vocab(self) -> Set:
        return vocabs.get_words_vocab()

    def is_trivial(self) -> bool:
        return True


def make_token_abbreviation(sop: rasp.SOp) -> rasp.SOp:
    """
    Creates abbreviations for each token in the sequence.

    Example usage:
      token_abbreviation = make_token_abbreviation(rasp.tokens)
      token_abbreviation(["international", "business", "machines"])
      >> ["int", "bus", "mac"]
    """
    abbreviation = rasp.Map(lambda x: x[:3] if len(x) > 3 else x, sop)
    return abbreviation
