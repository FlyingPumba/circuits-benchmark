from argparse import Namespace, ArgumentParser

import torch as t
from auto_circuit.data import PromptDataLoader, PromptDataset, PromptPairBatch
from auto_circuit.prune_algos.edge_attribution_patching import edge_attribution_patching_prune_scores
from auto_circuit.types import PruneScores
from auto_circuit.utils.graph_utils import patchable_model
from auto_circuit.utils.tensor_ops import prune_scores_threshold

from acdc.TLACDCCorrespondence import TLACDCCorrespondence
from circuits_benchmark.benchmark.benchmark_case import BenchmarkCase
from circuits_benchmark.benchmark.case_dataset import CaseDataset
from circuits_benchmark.commands.common_args import add_common_args
from circuits_benchmark.transformers.acdc_circuit_builder import build_acdc_circuit
from circuits_benchmark.utils.auto_circuit_utils import build_circuit
from circuits_benchmark.utils.circuits_comparison import calculate_fpr_and_tpr


class EAPRunner:
  def __init__(self, case: BenchmarkCase, args: Namespace):
    self.case = case
    self.args = args
    self.data_size = args.data_size
    self.edge_count = args.edge_count
    self.threshold = args.threshold

    assert self.edge_count is not None or self.threshold is not None, "Either edge_count or threshold must be provided"
    assert self.edge_count is None or self.threshold is None, "Only one of edge_count or threshold must be provided"

  def run_on_tracr_model(self):
    tl_model = self.case.get_tl_model()
    clean_dataset = self.case.get_clean_data(count=self.data_size)
    corrupted_dataset = self.case.get_corrupted_data(count=self.data_size)

    return self.run_eap(tl_model, clean_dataset, corrupted_dataset)

  def run_eap(self,
              tl_model: t.nn.Module,
              clean_dataset: CaseDataset,
              corrupted_dataset: CaseDataset):
    auto_circuit_model = patchable_model(
      tl_model,
      factorized=True,
      slice_output=None,
      separate_qkv=True,
      device=self.args.device,
    )

    # remove from inputs the rows that have the same expected output
    clean_raw_inputs = clean_dataset.get_inputs()
    corrupted_raw_inputs = corrupted_dataset.get_inputs()
    clean_expected_outputs = clean_dataset.get_correct_outputs()
    corrupted_expected_outputs = corrupted_dataset.get_correct_outputs()

    idxs_to_remove = []
    for i in range(len(clean_expected_outputs)):
      if clean_expected_outputs[i] == corrupted_expected_outputs[i]:
        idxs_to_remove.append(i)

    clean_inputs = [clean_raw_inputs[i] for i in range(len(clean_raw_inputs)) if i not in idxs_to_remove]
    corrupted_inputs = [corrupted_raw_inputs[i] for i in range(len(corrupted_raw_inputs)) if i not in idxs_to_remove]

    # Convert inputs to tensors using tracr encoder
    clean_inputs = tl_model.map_tracr_input_to_tl_input(clean_inputs)
    corrupted_inputs = tl_model.map_tracr_input_to_tl_input(corrupted_inputs)

    # Use as correct and wrong answers the output of tracr model on the filtered inputs
    with t.no_grad():
      if tl_model.is_categorical():
        clean_outputs = tl_model(clean_inputs).argmax(dim=-1).unsqueeze(dim=-1)
        corrupted_outputs = tl_model(corrupted_inputs).argmax(dim=-1).unsqueeze(dim=-1)
      else:
        clean_outputs = tl_model(clean_inputs)
        corrupted_outputs = tl_model(corrupted_inputs)

    dataset = PromptDataset(
      clean_inputs,
      corrupted_inputs,
      clean_outputs,
      corrupted_outputs,
    )
    train_loader = PromptDataLoader(dataset, seq_len=self.case.get_max_seq_len(), diverge_idx=0)

    if tl_model.is_categorical():
      # For categorical models we use as loss function the diff between the correct and wrong answers
      attribution_scores: PruneScores = edge_attribution_patching_prune_scores(
        model=auto_circuit_model,
        dataloader=train_loader,
        official_edges=None,
        answer_diff=True,
      )
    else:
      # Auto-circuit assumes that all models are categorical, so we need to provide a custom loss function for
      # regression ones
      def loss_fn(logits: t.Tensor, batch: PromptPairBatch) -> t.Tensor:
        return -t.mean(logits - batch.wrong_answers)

      attribution_scores: PruneScores = edge_attribution_patching_prune_scores(
        model=auto_circuit_model,
        dataloader=train_loader,
        official_edges=None,
        loss_fn=loss_fn,
      )

    if self.edge_count is not None:
      # find the threshold for the top-k edges
      threshold = prune_scores_threshold(attribution_scores, self.edge_count).item()
    else:
      threshold = self.threshold

    eap_circuit = build_circuit(auto_circuit_model, attribution_scores, threshold)
    eap_circuit.save(f"{self.args.output_dir}/final_circuit.pkl")

    print("Calculating FPR and TPR for threshold", threshold)
    full_corr = TLACDCCorrespondence.setup_from_model(tl_model, use_pos_embed=True)
    full_circuit = build_acdc_circuit(full_corr)
    tracr_hl_circuit, tracr_ll_circuit, alignment = self.case.get_tracr_circuit(granularity="acdc_hooks")
    result = calculate_fpr_and_tpr(eap_circuit, tracr_ll_circuit, full_circuit, verbose=True)

    return eap_circuit, result

  @staticmethod
  def setup_subparser(subparsers):
    parser = subparsers.add_parser("eap")
    EAPRunner.add_args_to_parser(parser)

  @staticmethod
  def add_args_to_parser(parser):
    add_common_args(parser)

    parser.add_argument("--using-wandb", action="store_true")
    parser.add_argument(
      "--wandb-project", type=str, default="subnetwork-probing"
    )
    parser.add_argument("--wandb-entity", type=str, required=False)
    parser.add_argument("--wandb-group", type=str, required=False)
    parser.add_argument("--wandb-dir", type=str, default="/tmp/wandb")
    parser.add_argument("--wandb-mode", type=str, default="online")
    parser.add_argument(
      "--wandb-run-name",
      type=str,
      required=False,
      default=None,
      help="Value for wandb_run_name",
    )

    parser.add_argument("--edge-count", type=int, default=None,
                        help="Number of edges to keep in the final circuit")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Threshold of effect to keep an edge in the final circuit")
    parser.add_argument("--data-size", type=int, default=1000, help="Number of samples to use")

  @classmethod
  def make_default_runner(cls, task: str):
    parser = ArgumentParser()
    cls.add_args_to_parser(parser)
    args = parser.parse_args([])
    return cls(task, args)
