import torch
import torch.nn as nn
import torch.nn.functional as F
import FaultyMemory.cluster as C
import FaultyMemory.handler as H

import wrn_mcdonnell_manual as McDo
import Dropit
from collections import OrderedDict

from tests.test_representation import test_binary_faults

test_binary_faults()

exit()

class SimpleNet(nn.Module):
    def __init__(self):
        super(SimpleNet, self).__init__()
        self.fc1 = nn.Linear(1,2)
        self.fc2 = nn.Linear(2,3)
        self.fc3 = nn.Linear(3,4)

    def forward(self, x):
        x = self.fc1(x)
        x = self.fc2(x)
        x = self.fc3(x)
        return x


class SimpleConv(nn.Module):
    def __init__(self):
        super(SimpleConv, self).__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2,2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)
        self.perturb = 1

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(-1, 16 * 5 * 5)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        return x


net = McDo.WRN_McDonnell(depth=28, width=10, num_classes=10, dropit=False, actprec=3)
# net = SimpleNet()


nb_clusters = 4
cluster_list = [C.Cluster() for _ in range(nb_clusters)]
print(cluster_list)
handler = H.Handler(net, cluster_list)

handler.from_json('./profiles/McDo.json')

handler.assign_clusters()
# handler.to_json('./profiles/saved_handler.json')
exit()
print(handler)

inp = torch.tensor([1.])
out = handler(inp)

print(handler)

print('out: ', out)


"""
def confint_mean_testset():
  top1avgs = []
  while True:
    top1avgs.append(test(model, loss_func, args.device, args.testloader, len(top1avgs), wm))
    confint = sms.DescrStatsW(top1avgs).tconfint_mean()
    if (confint[1]-confint[0] < args.confidence_interval_test and len(top1avgs)>5):
        break
"""
