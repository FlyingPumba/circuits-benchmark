import unittest

from utils.attr_dict import AttrDict
from utils.get_cases import get_cases


class GetCasesTest(unittest.TestCase):
  def test_all_cases(self):
    cases = get_cases(None)
    self.assertEqual(len(cases), 47)

  def test_cases_filtered_by_indices(self):
    args = AttrDict({"indices": "1,2,3"})
    cases = get_cases(args)
    self.assertEqual(len(cases), 3)

  def no_parent_directory_prefix(self):
    args = AttrDict({"indices": "1,2,3"})
    cases = get_cases(args)
    for case in cases:
      self.assertNotEqual(case.get_file_path_from_root()[:3], "../")