from argparse import Namespace
from typing import List

from circuits_benchmark.benchmark.benchmark_case import BenchmarkCase
from circuits_benchmark.utils.find_all_subclasses import find_all_subclasses_in_package


def get_cases(args: Namespace | None = None, indices: List[str] | None = None) -> List[BenchmarkCase]:
  assert (args is None or args.indices is None) or indices is None, "Cannot specify both args.indices and indices"

  classes = find_all_subclasses_in_package(BenchmarkCase, "circuits_benchmark.benchmark.cases")

  if args is not None and args.indices is not None:
    indices = args.indices.split(",")

  if indices is not None:
    # filter class names that are "CaseN" where N in indices
    classes = [cls for cls in classes if cls.__name__[4:] in indices]

  # sort classes numerically, knowing that the names are "CaseN" where N is a number
  classes.sort(key=lambda cls: int(cls.__name__[4:]))

  # instantiate all classes found
  return [cls() for cls in classes]
