from argparse import Namespace

from argparse_dataclass import ArgumentParser

from benchmark.benchmark_case import BenchmarkCase
from commands.common_args import add_common_args
from commands.train.auto_compression import run_auto_compression_training
from training.compression.linear_compressed_tracr_transformer import LinearCompressedTracrTransformer, \
  linear_compression_initialization_options
from training.compression.linear_compressed_tracr_transformer_trainer import LinearCompressedTracrTransformerTrainer
from training.training_args import TrainingArgs
from utils.hooked_tracr_transformer import HookedTracrTransformer


def setup_args_parser(subparsers):
  parser = subparsers.add_parser("linear-compression")
  add_common_args(parser)

  parser.add_argument("--residual-stream-compression-size", type=str, default="auto",
                      help="A list of comma separated sizes for the compressed residual stream, or 'auto' to find the "
                           "optimal size.")
  parser.add_argument("--auto-compression-accuracy", type=float, default=0.95,
                      help="The desired test accuracy when using 'auto' compression size.")
  parser.add_argument("--linear-compression-initialization", type=str, default="linear",
                      choices=linear_compression_initialization_options,
                      help="The initialization method for the linear compression matrix.")


def run_single_linear_compression_training(case: BenchmarkCase,
                                           tl_model: HookedTracrTransformer,
                                           args: Namespace,
                                           compression_size: int):
  initialization = args.linear_compression_initialization
  training_args, _ = ArgumentParser(TrainingArgs).parse_known_args(args.original_args)

  print(f" >>> Starting linear compression for {case} with residual stream compression size {compression_size}.")
  compressed_tracr_transformer = LinearCompressedTracrTransformer(
    tl_model,
    int(compression_size),
    initialization,
    tl_model.device)

  trainer = LinearCompressedTracrTransformerTrainer(case, tl_model, compressed_tracr_transformer, training_args,
                                                    output_dir=args.output_dir)
  final_metrics = trainer.train()
  print(f" >>> Final metrics for {case} with residual stream compression size {compression_size}: ")
  print(final_metrics)

  return final_metrics


def train_linear_compression(case: BenchmarkCase, args: Namespace):
  """Compresses the residual stream of a Tracr model using a linear compression."""
  tl_model: HookedTracrTransformer = case.get_tl_model()
  run_auto_compression_training(case, tl_model, args, run_single_linear_compression_training)
