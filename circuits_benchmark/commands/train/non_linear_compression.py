from argparse import Namespace

from torch.nn import init

from circuits_benchmark.benchmark.benchmark_case import BenchmarkCase
from circuits_benchmark.commands.common_args import add_common_args
from circuits_benchmark.commands.train.auto_compression import run_auto_compression_training
from circuits_benchmark.training.compression.autencoder import AutoEncoder
from circuits_benchmark.training.compression.autoencoder_trainer import AutoEncoderTrainer
from circuits_benchmark.training.compression.compression_train_loss_level import compression_train_loss_level_options
from circuits_benchmark.training.compression.non_linear_compressed_tracr_transformer_trainer import \
  NonLinearCompressedTracrTransformerTrainer
from circuits_benchmark.training.training_args import TrainingArgs
from circuits_benchmark.transformers.hooked_tracr_transformer import HookedTracrTransformer


def setup_args_parser(subparsers):
  parser = subparsers.add_parser("non-linear-compression")
  add_common_args(parser)

  parser.add_argument("--residual-stream-compression-size", type=str, default="auto",
                      help="A list of comma separated sizes for the compressed residual stream, or 'auto' to find the "
                           "optimal size.")
  parser.add_argument("--auto-compression-accuracy", type=float, default=0.95,
                      help="The desired test accuracy when using 'auto' compression size.")
  parser.add_argument("--train-loss", type=str, default="layer", choices=compression_train_loss_level_options,
                      help="The train loss level for the compression training.")
  parser.add_argument("--ae-path", type=str, default=None,
                      help="Path to trained AutoEncoder model.")

  parser.add_argument("--ae-layers", type=int, default=2,
                      help="The desired number of layers for the autoencoder.")
  parser.add_argument("--ae-first-hidden-layer-shape", type=str, default="wide", choices=["wide", "narrow"],
                      help="The desired shape for the first hidden layer of the autoencoder. Wide means larger than "
                           "the input layer. Narrow means smaller than the input layer.")

  parser.add_argument("--ae-epochs", type=int, default=70,
                      help="The number of epochs to use for initial autoencoder training.")
  parser.add_argument("--ae-batch-size", type=int, default=2**12,
                      help="The batch size to use for initial autoencoder training.")
  parser.add_argument("--ae-lr-start", type=float, default=0.01,
                      help="The number of epochs to use for initial autoencoder training.")

  parser.add_argument("--freeze-ae-weights", action="store_true", default=False,
                      help="Freeze the weights of the autoencoder during the non-linear compression training.")
  parser.add_argument("--ae-training-epochs-gap", type=int, default=10,
                      help="The number of epochs to wait before training the autoencoder again.")
  parser.add_argument("--ae-max-training-epochs", type=int, default=15,
                      help="The max number of epochs to use for training when autoencoder weights are not frozen.")
  parser.add_argument("--ae-desired-test-mse", type=float, default=1e-3,
                      help="The desired test mean squared error for the autoencoder.")


def run_single_non_linear_compression_training(case: BenchmarkCase,
                                               tl_model: HookedTracrTransformer,
                                               args: Namespace,
                                               training_args: TrainingArgs,
                                               compression_size: int):
  original_residual_stream_size = tl_model.cfg.d_model

  new_tl_model = HookedTracrTransformer.from_hooked_tracr_transformer(
    tl_model,
    overwrite_cfg_dict={"d_model": compression_size},
    init_params_fn=lambda x: init.kaiming_uniform_(x) if len(x.shape) > 1 else init.normal_(x, std=0.02),
  )

  autoencoder = AutoEncoder(original_residual_stream_size,
                            compression_size,
                            args.ae_layers,
                            args.ae_first_hidden_layer_shape)
  if args.ae_path is not None:
    # Load AutoEncoder model weights
    autoencoder.load_weights_from_file(args.ae_path)
  else:
    # Train an AutoEncoder model
    ae_training_args = TrainingArgs()
    ae_training_args.seed = args.seed
    ae_training_args.epochs = args.ae_epochs
    ae_training_args.lr_start = args.ae_lr_start
    ae_training_args.batch_size = args.ae_batch_size
    ae_training_args.test_data_ratio = training_args.test_data_ratio
    ae_training_args.train_data_size = training_args.train_data_size
    ae_training_args.early_stop_test_accuracy = training_args.early_stop_test_accuracy if training_args.early_stop_test_accuracy is not None else 0.97
    ae_training_args.lr_patience = 15

    print(
      f" >>> Starting AutoEncoder training for {case} with residual stream compression size {compression_size}.")
    trainer = AutoEncoderTrainer(case, autoencoder, tl_model, ae_training_args,
                                 train_loss_level=args.train_loss,
                                 output_dir=args.output_dir)
    final_metrics = trainer.train()
    print(f" >>> Final metrics for {case}'s autoencoder with residual stream compression size {compression_size}: ")
    print(final_metrics)

  print(f" >>> Starting transformer training for {case} non-linear compressed resid of size {compression_size}.")
  trainer = NonLinearCompressedTracrTransformerTrainer(case,
                                                       tl_model,
                                                       new_tl_model,
                                                       autoencoder,
                                                       training_args,
                                                       train_loss_level=args.train_loss,
                                                       output_dir=args.output_dir,
                                                       freeze_ae_weights=args.freeze_ae_weights,
                                                       ae_training_epochs_gap=args.ae_training_epochs_gap,
                                                       ae_desired_test_mse=args.ae_desired_test_mse,
                                                       ae_max_training_epochs=args.ae_max_training_epochs)
  final_metrics = trainer.train()
  print(f" >>> Final metrics for {case}'s non-linear compressed transformer with resid size {compression_size}: ")
  print(final_metrics)

  return final_metrics


def train_non_linear_compression(case: BenchmarkCase, args: Namespace):
  """Compresses the residual stream of a Tracr model using a linear compression."""
  tl_model: HookedTracrTransformer = case.get_tl_model()
  run_auto_compression_training(case, tl_model, args, run_single_non_linear_compression_training)
