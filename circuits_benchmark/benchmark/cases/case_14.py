from typing import Set

from tracr.rasp import rasp

from circuits_benchmark.benchmark import vocabs
from circuits_benchmark.benchmark.program_evaluation_type import causal_and_regular
from circuits_benchmark.benchmark.tracr_benchmark_case import TracrBenchmarkCase


class Case14(TracrBenchmarkCase):
    def get_program(self) -> rasp.SOp:
        return make_count(rasp.tokens, "a")

    def get_task_description(self) -> str:
        return "Returns the count of 'a' in the input sequence."

    def supports_causal_masking(self) -> bool:
        return False

    def get_vocab(self) -> Set:
        return vocabs.get_ascii_letters_vocab(count=3)


@causal_and_regular
def make_count(sop, token):
    """Returns the count of `token` in `sop`.

    The output sequence contains this count in each position.

    Example usage:
      count = make_count(tokens, "a")
      count(["a", "a", "a", "b", "b", "c"])
      >> [3, 3, 3, 3, 3, 3]
      count(["c", "a", "b", "c"])
      >> [1, 1, 1, 1]

    Args:
      sop: Sop to count tokens in.
      token: Token to count.
    """
    return rasp.SelectorWidth(rasp.Select(
        sop, sop, lambda k, q: k == token)).named(f"count_{token}")
