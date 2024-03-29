import dataclasses
import sys
from typing import List, Dict

import numpy as np
import torch as t
import wandb
from jaxtyping import Float
from torch import Tensor
from torch.nn import Parameter
from torch.optim.lr_scheduler import ReduceLROnPlateau
from torch.utils.data import DataLoader
from tqdm import tqdm

from circuits_benchmark.benchmark.benchmark_case import BenchmarkCase
from circuits_benchmark.training.training_args import TrainingArgs
from circuits_benchmark.transformers.hooked_tracr_transformer import HookedTracrTransformerBatchInput


class GenericTrainer:

  def __init__(self,
               case: BenchmarkCase,
               parameters: List[Parameter],
               training_args: TrainingArgs,
               output_dir: str | None = None):
    self.case = case
    self.parameters = parameters
    self.args = training_args
    self.output_dir = output_dir

    self.wandb_run = None
    self.use_wandb = self.args.wandb_project is not None

    self.step = 0
    self.epoch = 0
    self.train_loss = np.nan
    self.test_metrics = {}
    self.training_progress_bar = None

    self.train_loader: DataLoader = None
    self.test_loader: DataLoader = None
    self.setup_dataset()

    # calculate number of epochs and steps
    assert self.args.epochs is not None or self.args.steps is not None, "Must specify either epochs or steps."
    assert self.args.epochs is None or self.args.steps is None, "Cannot specify both epochs and steps."

    if self.args.epochs is not None:
      self.epochs = self.args.epochs
      self.steps = self.epochs * len(self.train_loader)

    if self.args.steps is not None:
      self.epochs = (self.steps // len(self.train_loader)) + 1
      self.steps = self.args.steps

    # assert at least one parameter
    assert len(self.parameters) > 0, "No parameters to optimize."

    # get the device from parameters
    self.device = self.parameters[0].device

    self.optimizer = t.optim.AdamW(self.parameters,
                                   lr=self.args.lr_start,
                                   weight_decay=self.args.weight_decay,
                                   betas=(self.args.beta_1, self.args.beta_2))

    # We will set up the learning rate scheduler to look at the test accuracy metric. The learning rate will be reduced
    # by a given factor (default 0.9) if the test accuracy does not improve at least by some threshold (default 0.005)
    # in a given number of epochs (default 500).
    self.lr_scheduler = ReduceLROnPlateau(self.optimizer,
                                          factor=self.args.lr_factor,
                                          patience=self.args.lr_patience,
                                          mode="max",
                                          threshold_mode="abs",
                                          threshold=self.args.lr_threshold)

    if self.use_wandb and self.args.wandb_name is None:
      self.args.wandb_name = self.build_wandb_name()

    print(f"Training with args: {self.args}")
    print(f"Will run for {self.epochs} epochs ({self.steps} steps).")


  def setup_dataset(self):
    """Prepare the dataset and split it into train and test sets."""
    raise NotImplementedError

  def train(self):
    """
    Trains the model, for `self.args.epochs` epochs.
    """
    if self.use_wandb:
      self.wandb_run = wandb.init(project=self.args.wandb_project,
                                  name=self.args.wandb_name,
                                  config=self.get_wandb_config(),
                                  tags=self.get_wandb_tags(),
                                  notes=self.get_wandb_notes())
      self.define_wandb_metrics()

    self.training_progress_bar = tqdm(total=len(self.train_loader) * self.epochs)
    for i in range(self.epochs):
      self.epoch = i

      if self.use_wandb:
        wandb.log({
          "lr": self.optimizer.param_groups[0]["lr"],
          "epoch": self.epoch
        }, step=self.step)

      self.training_epoch()

      # compute test metrics and update learning rate using them
      with t.no_grad():
        self.compute_test_metrics()

      self.lr_scheduler.step(self.get_lr_validation_metric())

      if (self.args.early_stop_test_accuracy is not None and
          self.test_metrics["test_accuracy"] >= self.args.early_stop_test_accuracy):
        break

    if self.output_dir is not None:
      self.save_artifacts()

    if self.use_wandb:
      wandb.finish()

    return {**self.test_metrics, "train_loss": self.train_loss.item()}

  def training_epoch(self):
    for i, batch in enumerate(self.train_loader):
      self.train_loss = self.training_step(batch)
      self.training_progress_bar.update()
      self.training_progress_bar.set_description(f"Epoch {self.epoch}, train_loss: {self.train_loss:.3f}" +
                                                 self.build_test_metrics_string())

  def training_step(self, inputs) -> Float[Tensor, ""]:
    """Calculates the loss on batched inputs, performs a gradient update step, and logs the loss."""
    self.optimizer.zero_grad()

    loss = self.compute_train_loss(inputs)

    self.update_params(loss)

    self.step += 1

    return loss

  def update_params(self, loss: Float[Tensor, ""]):
    """Performs a gradient update step."""
    loss.backward()
    self.optimizer.step()

  def compute_train_loss(self, batch: Dict[str, HookedTracrTransformerBatchInput]) -> Float[Tensor, ""]:
    raise NotImplementedError

  def compute_test_metrics(self):
    raise NotImplementedError

  def get_lr_validation_metric(self):
    return self.test_metrics["test_accuracy"]

  def build_test_metrics_string(self):
    if len(self.test_metrics.items()) == 0:
      return ""
    else:
      return ", " + ("".join([f"{k}: {v:.3f}, " for k, v in self.test_metrics.items()]))[:-2]

  def build_wandb_name(self):
    return f"case-{self.case.get_index()}-generic-training"

  def define_wandb_metrics(self):
    wandb.define_metric("train_loss", summary="min")
    wandb.define_metric("test_accuracy", summary="max")

  def get_wandb_tags(self):
    return [f"case{self.case.get_index()}"]

  def get_wandb_notes(self):
    return f"Command: {' '.join(sys.argv)}"

  def get_wandb_config(self):
    cfg = dataclasses.asdict(self.args)
    cfg.update({
      "resolved_epochs": self.epochs,
      "resolved_steps": self.steps,
      "case": self.case.get_index()
    })
    return cfg

  def save_artifacts(self):
    pass