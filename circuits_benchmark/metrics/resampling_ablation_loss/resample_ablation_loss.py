import gc
from dataclasses import dataclass
from typing import List

import numpy as np
import torch as t
from jaxtyping import Float
from torch import Tensor
from transformer_lens import HookedTransformer

from circuits_benchmark.benchmark.case_dataset import CaseDataset
from circuits_benchmark.metrics.resampling_ablation_loss.intervention import InterventionData
from circuits_benchmark.metrics.resampling_ablation_loss.resample_ablation_interventions import get_interventions
from circuits_benchmark.training.compression.residual_stream_mapper.residual_stream_mapper import ResidualStreamMapper


@dataclass
class ResampleAblationLossOutput:
  loss: Float[Tensor, ""]
  variance_explained: Float[Tensor, ""]


def get_resample_ablation_loss_from_inputs(
    clean_inputs: CaseDataset,
    corrupted_inputs: CaseDataset,
    base_model: HookedTransformer,
    hypothesis_model: HookedTransformer,
    residual_stream_mapper: ResidualStreamMapper | None = None,
    hook_filters: List[str] | None = None,
    batch_size: int = 2048,
    max_interventions: int = 10
) -> ResampleAblationLossOutput:
  # assert that clean_input and corrupted_input have the same length
  assert len(clean_inputs) == len(corrupted_inputs), "clean and corrupted inputs should have same length."
  # assert that clean and corrupted inputs are not exactly the same, otherwise the comparison is flawed.
  assert clean_inputs != corrupted_inputs, "clean and corrupted inputs should have different data."

  # Build data for interventions before starting to avoid recomputing the same data for each intervention.
  batched_intervention_data = get_batched_intervention_data(clean_inputs,
                                                            corrupted_inputs,
                                                            base_model,
                                                            hypothesis_model,
                                                            residual_stream_mapper,
                                                            batch_size)

  return get_resample_ablation_loss(batched_intervention_data, base_model, hypothesis_model, residual_stream_mapper,
                                    hook_filters, max_interventions)


def get_resample_ablation_loss(batched_intervention_data: List[InterventionData],
                               base_model: HookedTransformer,
                               hypothesis_model: HookedTransformer,
                               residual_stream_mapper: ResidualStreamMapper | None,
                               hook_filters: List[str] | None = None,
                               max_interventions: int = 10):
  # This is a memory intensive operation, so we will garbage collect before starting.
  gc.collect()
  t.cuda.empty_cache()

  if hook_filters is None:
    # by default, we use the following hooks for the intervention points.
    # This will give 2 + n_layers * 2 intervention points.
    hook_filters = ["hook_embed", "hook_pos_embed", "hook_attn_out", "hook_mlp_out"]

  # we assume that both models have the same architecture. Otherwise, the comparison is flawed since they have different
  # intervention points.
  assert base_model.cfg.n_layers == hypothesis_model.cfg.n_layers
  assert base_model.cfg.n_heads == hypothesis_model.cfg.n_heads
  assert base_model.cfg.n_ctx == hypothesis_model.cfg.n_ctx
  assert base_model.cfg.d_vocab == hypothesis_model.cfg.d_vocab

  assert max_interventions > 0, "max_interventions should be greater than 0."

  # Calculate the variance of the base model logits.
  base_model_logits_variance = []
  for intervention_data in batched_intervention_data:
    clean_inputs_batch = intervention_data.clean_inputs
    base_model_logits = base_model(clean_inputs_batch)
    base_model_logits_variance.append(t.var(base_model_logits).item())
  base_model_logits_variance = np.mean(base_model_logits_variance)

  # for each intervention, run both models, calculate MSE and add it to the losses.
  losses = []
  variance_explained = []
  for intervention in get_interventions(base_model,
                                        hypothesis_model,
                                        hook_filters,
                                        residual_stream_mapper,
                                        max_interventions):
    # We may have more than one batch of inputs, so we need to iterate over them, and average at the end.
    intervention_losses = []
    intervention_variance_explained = []
    for intervention_data in batched_intervention_data:
      clean_inputs_batch = intervention_data.clean_inputs

      with intervention.hooks(base_model, hypothesis_model, intervention_data):
        base_model_logits = base_model(clean_inputs_batch)
        hypothesis_model_logits = hypothesis_model(clean_inputs_batch)

        loss = t.nn.functional.mse_loss(base_model_logits, hypothesis_model_logits)
        var_explained = 1 - loss / base_model_logits_variance

        intervention_losses.append(loss.reshape(1))
        intervention_variance_explained.append(var_explained.reshape(1))

    losses.append(t.cat(intervention_losses).mean().reshape(1))
    variance_explained.append(t.cat(intervention_variance_explained).mean().reshape(1))

  return ResampleAblationLossOutput(loss=t.cat(losses).mean(), variance_explained=t.cat(variance_explained).mean())


def get_batched_intervention_data(
    clean_inputs: CaseDataset,
    corrupted_inputs: CaseDataset,
    base_model: HookedTransformer,
    hypothesis_model: HookedTransformer,
    residual_stream_mapper: ResidualStreamMapper | None = None,
    batch_size: int = 2048,
) -> List[InterventionData]:
  data = []

  for clean_inputs_batch, corrupted_inputs_batch in zip(clean_inputs.get_inputs_loader(batch_size),
                                                        corrupted_inputs.get_inputs_loader(batch_size)):
    clean_inputs_batch = clean_inputs_batch[CaseDataset.INPUT_FIELD]
    corrupted_inputs_batch = corrupted_inputs_batch[CaseDataset.INPUT_FIELD]

    # Run the corrupted inputs on both models and save the activation caches.
    _, base_model_corrupted_cache = base_model.run_with_cache(corrupted_inputs_batch)
    _, hypothesis_model_corrupted_cache = hypothesis_model.run_with_cache(corrupted_inputs_batch)

    base_model_clean_cache = None
    hypothesis_model_clean_cache = None
    if residual_stream_mapper is not None:
      # Run the clean inputs on both models and save the activation caches.
      _, base_model_clean_cache = base_model.run_with_cache(clean_inputs_batch)
      _, hypothesis_model_clean_cache = hypothesis_model.run_with_cache(clean_inputs_batch)

    intervention_data = InterventionData(clean_inputs_batch,
                                         base_model_corrupted_cache,
                                         hypothesis_model_corrupted_cache,
                                         base_model_clean_cache,
                                         hypothesis_model_clean_cache)
    data.append(intervention_data)

  return data
