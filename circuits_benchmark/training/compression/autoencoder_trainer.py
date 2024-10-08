import re

import torch as t
import wandb
from iit.model_pairs.ll_model import LLModel
from jaxtyping import Float
from torch import Tensor
from torch.utils.data import DataLoader

from circuits_benchmark.benchmark.benchmark_case import BenchmarkCase
from circuits_benchmark.benchmark.case_dataset import CaseDataset
from circuits_benchmark.training.compression.autencoder import AutoEncoder
from circuits_benchmark.training.generic_trainer import GenericTrainer
from circuits_benchmark.training.training_args import TrainingArgs


class AutoEncoderTrainer(GenericTrainer):
    ACTIVATIONS_FIELD = "activations"

    def __init__(self,
                 case: BenchmarkCase,
                 autoencoder: AutoEncoder,
                 tl_model: LLModel,
                 args: TrainingArgs,
                 dataset: CaseDataset,
                 hook_name_filter_for_input_activations: str | None = None,
                 output_dir: str | None = None):
        self.autoencoder = autoencoder
        self.tl_model = tl_model
        self.tl_model_n_layers = tl_model.cfg.n_layers
        self.dataset = dataset
        self.hook_name_for_input_activations = hook_name_filter_for_input_activations
        super().__init__(case, list(autoencoder.parameters()), args, output_dir=output_dir)

    def setup_dataset(self):
        named_data = {}

        # We can't always use all the data, since it can lead to memory errors
        input_samples = min(int(self.args.max_train_samples * (1 + self.args.test_data_ratio)),
                            len(self.dataset))
        train_loader = self.dataset.make_loader(batch_size=input_samples, shuffle=True)
        inputs = next(iter(train_loader))[0]

        if self.hook_name_for_input_activations is None:
            _, activations_cache = self.tl_model.run_with_cache(
                inputs,
                names_filter=lambda
                    name: "attn_out" in name or "mlp_out" in name or "embed" in name or "pos_embed" in name
            )

            # collect the output of the attention and mlp components from all layers
            for layer in range(self.tl_model_n_layers):
                named_data[f"layer_{layer}_attn_out"] = activations_cache["attn_out", layer]
                named_data[f"layer_{layer}_mlp_out"] = activations_cache["mlp_out", layer]

            # collect the embeddings, but repeat the data self.tl_model_n_layers times
            named_data["embed"] = activations_cache["hook_embed"].repeat(self.tl_model_n_layers, 1, 1)
            named_data["pos_embed"] = activations_cache["hook_pos_embed"].repeat(self.tl_model_n_layers, 1, 1)

        else:
            str_for_regex = self.hook_name_for_input_activations.split("[")[0]
            regex = re.compile(f"^{str_for_regex}$")

            _, activations_cache = self.tl_model.run_with_cache(
                inputs,
                names_filter=lambda name: regex.match(name) is not None
            )

            assert len(
                activations_cache) > 0, f"No activations found for hook name filter: {self.hook_name_for_input_activations}"

            for hook_name in self.tl_model.hook_dict.keys():
                if regex.match(hook_name):
                    data = activations_cache[hook_name]
                    if "[" in self.hook_name_for_input_activations:
                        # extract the head index
                        head_index = int(self.hook_name_for_input_activations.split("[")[1].split("]")[0])
                        data = data[:, :, head_index, :]

                    named_data[hook_name] = data
                    break

        # Shape of tensors is [activations_len, seq_len, d_model]. We will convert to [activations_len, d_model] to
        # treat the residual stream for each sequence position as a separate sample.
        # The final length of all activations together is train_data_size*(n_layers + 1)*seq_len
        for name, data in named_data.items():
            named_data[name]: Float[Tensor, "activations_len, seq_len, d_model"] | Float[
                Tensor, "activations_len, seq_len, d_head"] = (
                data.transpose(0, 1).reshape(-1, data.shape[-1]))

        # split the data into train and test sets
        self.named_test_data = {}
        self.named_train_data = {}
        if self.args.test_data_ratio is not None:
            # split the data into train and test sets
            for name, data in named_data.items():
                data_size = data.shape[0]
                test_data_size = int(data_size * self.args.test_data_ratio)
                train_data_size = data_size - test_data_size
                self.named_train_data[name], self.named_test_data[name] = t.split(data,
                                                                                  [train_data_size, test_data_size])
        else:
            # use all data for training, and the same data for testing
            for name, data in named_data.items():
                self.named_train_data[name] = data.clone()
                self.named_test_data[name] = data.clone()

        # shuffle the activations in train and test data
        for name, data in self.named_train_data.items():
            self.named_train_data[name] = data[t.randperm(len(data))]
        for name, data in self.named_test_data.items():
            self.named_test_data[name] = data[t.randperm(len(data))]

        # collect all the train data into a single tensor
        train_data = t.cat(list(self.named_train_data.values()), dim=0)
        self.batch_size = self.args.batch_size if self.args.batch_size is not None else len(train_data)
        self.train_loader = DataLoader(train_data, batch_size=self.batch_size, shuffle=True)

    def compute_train_loss(self, batch: Float[Tensor, "batch_size d_model"]) -> Float[Tensor, "batch posn-1"]:
        output = self.autoencoder(batch)

        loss = t.nn.functional.mse_loss(batch, output)

        if self.use_wandb:
            wandb.log({"train_loss": loss}, step=self.step)

        return loss

    def compute_test_metrics(self):
        # compute MSE and accuracy on each batch and take average at the end
        test_mse = t.tensor(0.0, device=self.device)
        test_accuracy = t.tensor(0.0, device=self.device)
        test_batches = 0

        for name, test_data in self.named_test_data.items():
            self.test_loader = DataLoader(test_data, batch_size=self.batch_size, shuffle=False)

            named_mse = t.tensor(0.0, device=self.device)
            named_accuracy = t.tensor(0.0, device=self.device)
            batches = 0

            for inputs in self.test_loader:
                outputs = self.autoencoder(inputs)

                named_mse = named_mse + t.nn.functional.mse_loss(inputs, outputs)
                named_accuracy = named_accuracy + t.isclose(inputs, outputs,
                                                            atol=self.args.test_accuracy_atol).float().mean()

                batches = batches + 1
                test_batches = test_batches + 1

            test_mse = test_mse + named_mse
            test_accuracy = test_accuracy + named_accuracy

            named_mse = named_mse / batches
            self.test_metrics[f"test_{name}_mse"] = named_mse.item()

        self.test_metrics["test_mse"] = (test_mse / test_batches).item()
        self.test_metrics["test_accuracy"] = (test_accuracy / test_batches).item()

        if self.use_wandb:
            wandb.log(self.test_metrics, step=self.step)

    def build_wandb_name(self):
        return f"case-{self.case.get_name()}-autoencoder-{self.autoencoder.compression_size}"

    def get_wandb_tags(self):
        tags = super().get_wandb_tags()
        tags.append("autoencoder-trainer")
        return tags

    def get_wandb_config(self):
        cfg = super().get_wandb_config()
        cfg.update({
            "ae_input_size": self.autoencoder.input_size,
            "ae_compression_size": self.autoencoder.compression_size,
            "ae_layers": self.autoencoder.n_layers,
            "ae_first_hidden_layer_shape": self.autoencoder.first_hidden_layer_shape,
            "ae_use_bias": self.autoencoder.use_bias,
        })
        return cfg

    def save_artifacts(self):
        prefix = f"case-{self.case.get_name()}-resid-{self.autoencoder.compression_size}"
        self.autoencoder.save(self.output_dir, prefix, self.wandb_run)
