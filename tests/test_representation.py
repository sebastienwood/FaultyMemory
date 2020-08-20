import pytest
import torch
import numpy as np
import torch.nn as nn

from FaultyMemory.representation import BinaryRepresentation
from FaultyMemory.handler import Handler
from FaultyMemory.perturbator import BitwisePert

def test_binary_faults():
    class dummy_module(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_parameter('dummy', nn.Parameter(torch.empty(10).normal_(0,3)))

        def forward(self, x):
            return x * self.dummy
    
    dummy = dummy_module()
    bin_repr = BinaryRepresentation(width=1, unsigned=False)
    handler = Handler(dummy)
    handler.add_tensor('dummy', representation=bin_repr)
    handler.perturb_tensors()
    
    # no faults
    perturbed_ten = dummy.dummy.detach().numpy()
    assert (perturbed_ten == -1).all() or (perturbed_ten == 1).all()

    handler.restore()
    handler.remove_tensor('dummy')
    pert = BitwisePert()
    handler.add_tensor('dummy', representation=bin_repr, perturb=pert)
    handler.perturb_tensors()

    # faults everywhere : should sum to 0 (-1+1 for each slot of the tensor)
    perturbed_ten_inv = dummy.dummy.detach().numpy()
    assert sum(perturbed_ten + perturbed_ten_inv) == 0