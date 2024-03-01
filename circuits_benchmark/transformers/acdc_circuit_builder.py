from acdc.TLACDCCorrespondence import TLACDCCorrespondence
from circuits_benchmark.transformers.circuit import Circuit


def build_acdc_circuit(corr: TLACDCCorrespondence) -> Circuit:
  circuit = Circuit()

  for (child_name, child_index, parent_name, parent_index), edge in corr.all_edges().items():
    if edge.present:
      from_node = f"{parent_name}{str(parent_index)}"
      to_node = f"{child_name}{str(child_index)}"
      circuit.add_edge(from_node, to_node)

  return circuit
