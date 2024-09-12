import random

from circuits_benchmark.utils.circleci import is_running_in_circleci
from circuits_benchmark.utils.get_cases import get_cases


class TestCorrespondence:
    def test_get_corr_works_on_all_cases(self):
        cases = get_cases()

        if is_running_in_circleci():
            # randomly select 25% of the cases to run on CircleCI (no replacement)
            cases = random.sample(cases, int(0.25 * len(cases)))

        for case in cases:
            corr = case.get_correspondence()
            assert corr is not None
