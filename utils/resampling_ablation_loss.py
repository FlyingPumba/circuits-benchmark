from functools import partial
from typing import List

import torch as t
from jaxtyping import Float
from torch import Tensor
from transformer_lens import HookedTransformer, ActivationCache
from transformer_lens.hook_points import HookPoint

from utils.hooked_tracr_transformer import HookedTracrTransformerBatchInput


def get_resampling_ablation_loss(
    clean_inputs: HookedTracrTransformerBatchInput,
    corrupted_inputs: HookedTracrTransformerBatchInput,
    base_model: HookedTransformer,
    hypothesis_model: HookedTransformer,
    intervention_filters: List[str] = ["hook_embed", "hook_attn_out", "hook_mlp_out"]
) -> Float[Tensor, ""]:
  # we assume that both models have the same architecture. Otherwise, the comparison is flawed since they have different
  # intervention points.
  assert base_model.cfg.n_layers == hypothesis_model.cfg.n_layers
  assert base_model.cfg.n_heads == hypothesis_model.cfg.n_heads
  assert base_model.cfg.n_ctx == hypothesis_model.cfg.n_ctx
  assert base_model.cfg.d_vocab == hypothesis_model.cfg.d_vocab

  # assert that clean and corrupted inputs are not exactly the same, otherwise the comparison is flawed.
  all_equal = all(clean_input == corrupted_input
                  for clean_input, corrupted_input in zip(clean_inputs, corrupted_inputs))
  assert not all_equal, "clean and corrupted inputs are exactly the same. This is not a valid comparison."

  # first, we run the corrupted inputs on both models and save the activation caches.
  _, base_model_corrupted_cache = base_model.run_with_cache(corrupted_inputs)
  _, hypothesis_model_corrupted_cache = hypothesis_model.run_with_cache(corrupted_inputs)

  # for each intervention point in both models
  base_model_outputs = []
  hypothesis_model_outputs = []
  for hook_name, hook in base_model.hook_dict.items():
    assert hook_name in hypothesis_model.hook_dict, f"hook {hook_name} not found in hypothesis model."

    if intervention_filters is not None and not any([filter in hook_name for filter in intervention_filters]):
      # skip this hook point
      continue

    def corrupted_output_hook_fn(
        residual_stream: Float[Tensor, "batch seq_len d_model"],
        hook: HookPoint,
        corrupted_cache: ActivationCache = None
    ):
      return corrupted_cache[hook.name]

    # We intervene both models at the same point, run them on the clean data and save the output.
    with base_model.hooks(fwd_hooks=[(hook_name,
                                      partial(corrupted_output_hook_fn,
                                              corrupted_cache=base_model_corrupted_cache))]):
      with hypothesis_model.hooks(fwd_hooks=[(hook_name,
                                              partial(corrupted_output_hook_fn,
                                                      corrupted_cache=hypothesis_model_corrupted_cache))]):
        base_model_logits = base_model(clean_inputs)
        hypothesis_model_logits = hypothesis_model(clean_inputs)

        base_model_outputs.append(base_model_logits)
        hypothesis_model_outputs.append(hypothesis_model_logits)

  # compare the outputs of both models, e.g., using KL divergence
  base_model_outputs = t.cat(base_model_outputs, dim=0)
  hypothesis_model_outputs = t.cat(hypothesis_model_outputs, dim=0)

  # use MSE to compare the outputs of both models
  loss = t.nn.functional.mse_loss(base_model_outputs, hypothesis_model_outputs)

  return loss
