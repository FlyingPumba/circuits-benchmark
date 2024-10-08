import os.path
import os.path
from typing import Optional, Callable

import torch as t
from iit.model_pairs.base_model_pair import BaseModelPair
from iit.utils.correspondence import Correspondence
from jaxtyping import Float
from torch import Tensor
from transformer_lens import HookedTransformer, HookedTransformerConfig
from transformer_lens.hook_points import HookedRootModule

from circuits_benchmark.benchmark.case_dataset import CaseDataset
from circuits_benchmark.utils.circuit.circuit import Circuit
from circuits_benchmark.utils.circuit.circuit_granularity import CircuitGranularity
from circuits_benchmark.utils.project_paths import detect_project_root


class BenchmarkCase(object):
    def get_name(self) -> str:
        class_name = self.__class__.__name__  # e.g. Case1
        assert class_name.startswith("Case")
        return class_name[4:].lower()

    def __str__(self):
        return self.get_case_file_absolute_path()

    def get_task_description(self) -> str:
        """Returns the task description for the benchmark case."""
        return ""

    def is_categorical(self) -> bool:
        """Returns whether the benchmark case is categorical."""
        raise NotImplementedError()

    def get_max_seq_len(self) -> int:
        """Returns the maximum sequence length for the benchmark case (including BOS)."""
        raise NotImplementedError()

    def is_trivial(self) -> bool:
        """Returns a boolean indicating whether the benchmark case is trivial or not.
        This flag indicates that the case is too simple to be used for any type of evaluation.
        For example, cases that only involve copying the input to the output are considered trivial, as well as cases that
        memorize the output for a given input.
        """
        return False

    def get_clean_data(self,
                       min_samples: Optional[int] = 10,
                       max_samples: Optional[int] = 10,
                       seed: Optional[int] = 42,
                       unique_data: Optional[bool] = False) -> CaseDataset:
        raise NotImplementedError()

    def get_corrupted_data(self,
                           min_samples: Optional[int] = 10,
                           max_samples: Optional[int] = 10,
                           seed: Optional[int] = 43,
                           unique_data: Optional[bool] = False) -> CaseDataset:
        raise NotImplementedError()

    def get_validation_metric(self,
                              ll_model: HookedTransformer,
                              data: t.Tensor,
                              *args, **kwargs) -> Callable[[Tensor], Float[Tensor, ""]]:
        """Returns the validation metric for the benchmark case."""
        raise NotImplementedError()

    def get_ll_model_cfg(self,
                         overwrite_cfg_dict: dict | None = None,
                         *args, **kwargs) -> HookedTransformerConfig:
        """Returns the configuration for the LL model for this benchmark case."""
        raise NotImplementedError()

    def build_model_pair(
        self,
        training_args: dict | None = None,
        ll_model: HookedTransformer | None = None,
        hl_model: HookedRootModule | None = None,
        hl_ll_corr: Correspondence | None = None,
        *args, **kwargs
    ) -> BaseModelPair:
        """Returns a model pair for training the LL model."""
        raise NotImplementedError()

    def get_ll_model(
        self,
        device: t.device = t.device("cuda") if t.cuda.is_available() else t.device("cpu"),
        overwrite_cfg_dict: dict | None = None,
        *args, **kwargs
    ) -> HookedTransformer:
        """Returns the untrained transformer_lens model for this case.
        In IIT terminology, this is the LL model before training."""
        raise NotImplementedError()

    def get_hl_model(
        self,
        device: str | t.device = t.device("cuda") if t.cuda.is_available() else t.device("cpu"),
        *args, **kwargs
    ) -> HookedRootModule:
        """Builds the transformer_lens reference model for this case.
        In IIT terminology, this is the HL model."""
        raise NotImplementedError()

    def get_correspondence(self, *args, **kwargs) -> Correspondence:
        """Returns the correspondence between the reference and the benchmark model."""
        raise NotImplementedError()

    def get_ll_gt_circuit(self, granularity: CircuitGranularity = "acdc_hooks", *args, **kwargs) -> Circuit:
        """Returns the ground truth circuit for the LL model."""
        raise NotImplementedError()

    def get_hl_gt_circuit(self, granularity: CircuitGranularity = "acdc_hooks", *args, **kwargs) -> Circuit:
        """Returns the ground truth circuit for the HL model."""
        raise NotImplementedError()

    def get_case_file_absolute_path(self) -> str:
        return os.path.join(detect_project_root(), self.get_relative_path_from_root())

    def get_relative_path_from_root(self) -> str:
        return f"circuits_benchmark/benchmark/cases/case_{self.get_name()}.py"
