import numpy as np
from torch.utils.data import Dataset, DataLoader
from iit.utils.config import DEVICE
import torch
from iit.utils.iit_dataset import IITDataset


class TracrDataset(Dataset):
    def __init__(self, data: np.ndarray, labels: np.ndarray):
        self.data = data
        self.labels = labels
        assert data.shape == labels.shape

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx], self.labels[idx]


def get_encoded_input_from_torch_input(xy, hl_model, device):
    """Encode input to the format expected by the model"""
    x, y = zip(*xy)
    encoded_x = hl_model.map_tracr_input_to_tl_input(x)

    # if hl_model.is_categorical():
    #     y = list(y)
    #     for i in range(len(y)):
    #         y[i] = [0] + hl_model.tracr_output_encoder.encode(y[i][1:])
    #     y = list(map(list, zip(*y)))
    #     y = torch.tensor(y, dtype=torch.long).transpose(0, 1)
    #     # print(y, y.shape)
    #     num_classes = len(hl_model.tracr_output_encoder.encoding_map.keys())
    #     y = torch.nn.functional.one_hot(y, num_classes=num_classes).float()
    # else:
    #     y = list(map(list, zip(*y)))
    #     y[0] = list(np.zeros(len(y[0])))
    #     y = torch.tensor(y, dtype=torch.float32).transpose(0, 1)
    with torch.no_grad():
        y = hl_model(encoded_x)
    
    if hl_model.is_categorical():
        # convert to one-hot
        y = torch.nn.functional.one_hot(y.argmax(dim=-1), num_classes=y.shape[-1]).float()

    intermediate_values = None
    return encoded_x.to(device), y.to(device), intermediate_values


class TracrIITDataset(IITDataset):
    def __init__(self, base_data, ablation_data, hl_model, seed=0, every_combination=False):
        super().__init__(base_data, ablation_data, seed, every_combination)
        self.hl_model = hl_model
        self.device = hl_model.cfg.device

    @staticmethod
    def collate_fn(batch, hl_model, device=DEVICE):
        base_input, ablation_input = zip(*batch)
        encoded_base_input = get_encoded_input_from_torch_input(base_input, hl_model, device)
        encoded_ablation_input = get_encoded_input_from_torch_input(ablation_input, hl_model, device)
        return encoded_base_input, encoded_ablation_input

    def make_loader(
        self,
        batch_size,
        num_workers,
    ) -> DataLoader:
        return DataLoader(
            self,
            batch_size=batch_size,
            shuffle=True,
            num_workers=num_workers,
            collate_fn=lambda x: self.collate_fn(x, self.hl_model, self.device),
        )


class TracrUniqueDataset(TracrIITDataset):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __getitem__(self, index):
        return self.base_data[index]

    def __len__(self):
        return len(self.base_data)

    @staticmethod
    def collate_fn(batch, hl_model, device=DEVICE):
        encoded_base_input = get_encoded_input_from_torch_input(batch, hl_model, device)
        return encoded_base_input


def create_dataset(case, hl_model, train_count=12000, test_count=3000):
    data = case.get_clean_data(count=train_count + test_count)
    inputs = data.get_inputs().to_numpy()
    outputs = data.get_correct_outputs().to_numpy()
    train_inputs = inputs[:train_count]
    test_inputs = inputs[train_count:]
    train_outputs = outputs[:train_count]
    test_outputs = outputs[train_count:]
    train_data = TracrDataset(train_inputs, train_outputs)
    test_data = TracrDataset(test_inputs, test_outputs)
    return TracrIITDataset(train_data, train_data, hl_model), TracrIITDataset(test_data, test_data, hl_model)


def get_unique_data(case):
    data = case.get_clean_data(count=50_000)
    test_inputs = data.get_inputs().to_numpy()
    test_outputs = data.get_correct_outputs().to_numpy()
    arr, idxs = np.unique([", ".join(i) for i in np.array(test_inputs)], return_inverse=True)
    # create indices that point to the first unique input
    all_possible_inputs = np.arange(arr.shape[0])
    # find the first occurence of all_possible_inputs in idxs
    first_occurences = [np.where(idxs == i)[0][0] for i in all_possible_inputs]

    unique_test_inputs = test_inputs[first_occurences]
    unique_test_outputs = test_outputs[first_occurences]
    assert len(unique_test_inputs) == len(unique_test_outputs)
    assert len(unique_test_inputs) == len(np.unique([", ".join(i) for i in np.array(test_inputs)]))
    assert len(np.unique([", ".join(i) for i in np.array(unique_test_inputs)])) == len(unique_test_inputs)

    unique_test_data = TracrDataset(unique_test_inputs, unique_test_outputs)
    return unique_test_data
