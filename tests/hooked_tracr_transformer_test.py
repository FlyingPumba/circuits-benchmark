import logging
import unittest

import jax
from tracr.compiler import compiling
from tracr.rasp import rasp

from circuits_benchmark.benchmark.common_programs import make_reverse
from circuits_benchmark.benchmark.vocabs import TRACR_BOS, TRACR_PAD
from circuits_benchmark.transformers.hooked_tracr_transformer import HookedTracrTransformer

# The default of float16 can lead to discrepancies between outputs of
# the compiled model and the RASP program.
jax.config.update('jax_default_matmul_precision', 'float32')
logging.basicConfig(level=logging.ERROR)


class HookedTracrTransformerTest(unittest.TestCase):
    def test_no_exception(self):
        # Fetch RASP program
        program = make_reverse(rasp.tokens)

        # Compile it to a transformer model
        tracr_output = compiling.compile_rasp_to_model(
            program,
            vocab={1, 2, 3},
            max_seq_len=5,
            compiler_bos=TRACR_BOS,
            compiler_pad=TRACR_PAD,
        )
        tracr_model = tracr_output.model

        input = [TRACR_BOS, 1, 2, 3, TRACR_PAD]
        print("Input:", input)

        tracr_output_decoded = tracr_model.apply(input).decoded
        print("Original Decoding:", tracr_output_decoded)

        tl_model = HookedTracrTransformer.from_tracr_model(tracr_model)
        tl_output_decoded = tl_model([input], return_type="decoded")[0]
        print("TransformerLens Replicated Decoding:", tl_output_decoded)

        self.assertEqual(tracr_output_decoded, tl_output_decoded)
