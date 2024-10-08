from typing import Set

from tracr.rasp import rasp

from circuits_benchmark.benchmark import vocabs
from circuits_benchmark.benchmark.common_programs import shift_by
from circuits_benchmark.benchmark.tracr_benchmark_case import TracrBenchmarkCase


class Case10(TracrBenchmarkCase):
    def get_program(self) -> rasp.SOp:
        return make_token_symmetry_checker(rasp.tokens)

    def get_task_description(self) -> str:
        return "Check if each word in a sequence is symmetric around its center."

    def get_vocab(self) -> Set:
        return vocabs.get_words_vocab().union({"radar", "rotor"})


def make_token_symmetry_checker(sop: rasp.SOp) -> rasp.SOp:
    """
    Checks if each token is symmetric around its center.

    Example usage:
      symmetry_checker = make_token_symmetry_checker(rasp.tokens)
      symmetry_checker(["radar", "apple", "rotor", "data"])
      >> [True, False, True, False]
    """
    half_length = rasp.Map(lambda x: len(x) // 2, sop)
    first_half = shift_by(half_length, sop)
    second_half = rasp.SequenceMap(lambda x, y: x[:y] == x[:-y - 1:-1], sop, half_length)
    symmetry_checker = rasp.SequenceMap(lambda x, y: x if y else None, sop, second_half)
    return symmetry_checker
