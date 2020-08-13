import torch
import torch.nn as nn
import torch.nn.functional as F
import copy
import math
import numpy as np
import perturbator as P
import representation as R
from hook import *
import cluster as C
import time
import json


class Handler():
    """
    Class in charge of saving tensors, storing information about them, activation perturbations and clusters.
    """
    def __init__(self, net, clusters=None):
        self.net = net
        self.saved_net = copy.deepcopy(net)
        self.clusters = clusters if clusters is not None else []
        self.modules = list(self.net.children())
        self.tensor_info = {}
        self.acti_info = {}
        self.hooks = {}

    def __str__(self):
        print("Handler: ")
        for name in self.tensor_info:
            print(name, ": ", self.tensor_info[name])
        return ''

    def __call__(self, x):
        return self.forward(x)

    def forward(self, x):
        r"""
        Saves every tensor, then perturbs every tensor, and then makes the forward pass
        """
        self.save_net()
        self.perturb_tensors()
        out =  self.net.forward(x)
        return out

    def restore(self):
        r"""
        Copies the modules' saved parameters back to the normal weights to allow for backpropagation
        """
        pert_params = list(self.net.parameters())
        saved_params = list(self.saved_net.parameters())
        for perturbed, saved in zip(pert_params, saved_params):
            perturbed_shape = perturbed.shape
            saved_shape = saved.shape
            perturbed = perturbed.flatten()
            saved = saved.flatten()
            for i, _ in enumerate(perturbed.data):
                    perturbed.data[i] = saved.data[i]
            perturbed = perturbed.view(perturbed_shape)
            saved = saved.view(saved_shape)

    def add_tensor(self, name, perturb=None, representation=None, reference=None):
        if reference is None:
            net_dict = dict(self.net.named_parameters())
            try:
                assert name in net_dict, "Specified name not in net.named_parameters and no reference given, cannot add this tensor"
                reference = dict(self.net.named_parameters())[name]    
            except AssertionError as id:
                print(id)
                return
        self.tensor_info[name] = (reference, perturb, representation)

    def remove_tensor(self, name):
        self.tensor_info.pop(name, None)

    def add_module(self, name, perturb=None, representation=None):
        net_dict = dict(self.net.named_modules())
        try:
            assert name in net_dict, "Specified name not in net.named_modules, cannot add this module"
        except AssertionError as id:
            print(id)
            return
        module = dict(self.net.named_modules())[name]
        for param_key in dict(module.named_parameters()):
            full_key = name + '.' + param_key
            self.add_tensor(full_key, perturb, representation)

    def remove_module(self, name):
        module = dict(self.net.named_modules())[name]
        for param_key in dict(module.named_parameters()):
            full_key = name + '.' + param_key
            self.remove_tensor(full_key)

    def add_network(self, perturb=[None], representation=None):
        for param_key in dict(self.net.named_parameters()):
            self.add_tensor(param_key, perturb, representation)

    def clear_network(self):
        for param_key in dict(self.net.named_parameters()):
            self.remove_tensor(param_key)

    def add_activation(self, name, perturb=None, representation=None):
        net_dict = dict(self.net.named_modules())
        try:
            assert name in net_dict, "Specified name not in net.named_modules, cannot add this module"
        except AssertionError as id:
            print(id)
            return
        module = net_dict[name]
        hook = Hook(perturb, representation)
        self.hooks[name] = module.register_forward_hook(hook.hook_fn)
        self.acti_info[name] = (perturb, representation)

    def add_network_activations(self, perturb=None, representation=None):
        for module in dict(self.net.named_modules()):
            self.add_activation(module)

    def init_clusters(self, clusters=None, modules=None): # TODO: DEPRECATED
        """
        This function is deprecated and should not be called
        Assigns modules to specified clusters.\n
        Clusters should contain the list of clusters you wish to assign modules to.\n
        Modules should be a list of lists of modules, the first list being the modules to assign to clusters[0] and so on.\n
        The list of modules in modules[i] will be assigned to clusters[i].\n
        If no modules or clusters are specified, it will split all modules in order and distribute them across all clusters in the handler equally.
        """
        if modules is None:
            if clusters is None:
                clusters = self.clusters   
            modules = list(self.net.children())
            nb_clust = len(clusters)
            nb_modules = len(modules)
            n = math.ceil(nb_modules/nb_clust)
            groups = [modules[i:i + n] for i in range(0, len(modules), n)]  # Splitting the modules in equal groups according to nb of clusters and nb of modules
            modules = groups

        for i, cluster in enumerate(clusters):
            for module in modules[i]:  # Watch out for out of bounds error
                cluster.add_module(module)
        
    def move_tensor(self, destination_cluster, tensor): # DEPRECATED
        """
        Moves a tensor from its cluster to the destination cluster
        """
        for cluster in self.clusters:
            if cluster.contains(tensor):
                cluster.remove_tensor(tensor)
        destination_cluster.add_tensor(tensor)

    def move_module(self, destination_cluster, module): # DEPRECATED
        """
        Moves a module from its cluster to the destination cluster
        """
        for cluster in self.clusters:
            cluster.remove_module(module)
        destination_cluster.add_module(module)

    def move_activation(self, destination_cluster, module): # DEPRECATED
        for cluster in self.clusters:
            cluster.remove_activation(module)
        destination_cluster.add_activation(module)

    def save_net(self):
        """
        Creates a backup of the network in saved_net
        """
        self.saved_net = copy.deepcopy(self.net)

    def perturb_tensors(self):
        """
        Applies every perturbation specified in their tensor_info to each tensor.\n
        Tensors are modified in-place, without modifying their reference.      
        """
        for name, item in self.tensor_info.items():
            tens = item[0]
            pert = item[1]
            repr = item[2]
            if pert is not None:
                for perturb in pert:
                    if perturb is not None:
                        perturb(tens, repr)

    def from_json(self, file_path):
        """
        Creates a handler dictionnary from a json file and initializes the handler to that configuration
        """
        with open(file_path) as file:
            jsonstr = file.read()
            handler_dict = json.loads(jsonstr)
            self.from_dict(handler_dict)

    def from_dict(self, handler_dict):
        """
        Loads a configuration from a dictionnary specifying the perturbations and representation of the entire network, modules or tensors\n
        Keys for modules have to be contained in net.named_modules() to be found\n
        Keys for tensors have to be contained in net.named_parameters() to be found\n
        An example of a dictionnary can be found in the file ./profiles/default.json
        """
        nb_clusters = handler_dict['nb_clusters']
        while len(self.clusters) < nb_clusters:
            self.clusters.append(C.Cluster())

        # Weights
        weight_dict = handler_dict['weights']
        if weight_dict is not None:
            # Network batch
            net = weight_dict['net']
            if net is not None:
                repr_dict = net['repr']
                repr = R.construct_repr(repr_dict)

                pert_list = net['perturb']
                perturbs = []
                if pert_list is not None:
                    for pert_dict in pert_list:
                        pert = P.construct_pert(pert_dict)
                        perturbs.append(pert)
                    
                for param in list(self.net.named_parameters()):
                    tensor_name = param[0]
                    self.tensor_info[tensor_name] = (param[1], perturbs, repr)

            # Modules batch
            modules = weight_dict['modules']
            if modules is not None:
                for module in modules:
                    module_name = module['name']

                    repr_dict = module['repr']
                    repr = R.construct_repr(repr_dict)

                    pert_list = module['perturb']
                    perturbs = []
                    for pert_dict in pert_list:
                        pert = P.construct_pert(pert_dict)
                        perturbs.append(pert)
                    
                    current_mod = dict(self.net.named_modules())[module_name]
                    for param_key in dict(current_mod.named_parameters()):
                        full_key = module_name + '.' + param_key
                        tens = dict(current_mod.named_parameters())[param_key]
                        self.tensor_info[full_key] = (tens, perturbs, repr)
                        
            # Tensors
            tensors = weight_dict['tensors']
            if tensors is not None:
                for tensor in tensors:
                    tensor_name = tensor['name']

                    repr_dict = tensor['repr']
                    repr = R.construct_repr(repr_dict)

                    pert_list = tensor['perturb']
                    perturbs = []
                    for pert_dict in pert_list:
                        pert = P.construct_pert(pert_dict)
                        perturbs.append(pert)

                    tens = dict(self.net.named_parameters())[tensor_name]
                    self.tensor_info[tensor_name] = (tens, perturbs, repr)

        # Activations
        acti_dict = handler_dict['activations']
        if acti_dict is not None:
            # Network batch
            net = acti_dict['net']
            if net is not None:
                repr_dict = net['repr']
                repr = R.construct_repr(repr_dict)

                pert_list = net['perturb']
                perturbs = []
                for pert_dict in pert_list:
                    pert = P.construct_pert(pert_dict)
                    perturbs.append(pert)

                for name, module in self.net.named_modules():
                    hook = Hook(perturbs, repr)
                    self.hooks[name] = module.register_forward_hook(hook.hook_fn)
                    self.acti_info[name] = (perturbs, repr)

            # Modules batch
            modules = acti_dict['modules']
            if modules is not None:
                for module in modules:
                    module_name = module['name']

                    repr_dict = module['repr']
                    repr = R.construct_repr(repr_dict)

                    pert_list = module['perturb']
                    perturbs = []
                    for pert_dict in pert_list:
                        pert = P.construct_pert(pert_dict)
                        perturbs.append(pert)
                    
                    current_mod = dict(self.net.named_modules())[module_name]
                    hook = Hook(perturbs, repr)
                    self.hooks[module_name] = current_mod.register_forward_hook(hook.hook_fn)
                    self.acti_info[module_name] = (perturbs, repr)

    def to_json(self, file_path):
        with open(file_path, 'w') as file:
            json.dump(self.to_dict(), file, indent="\t")

    def to_dict(self):
        handler_dict = {
            "nb_clusters" : len(self.clusters)
        }
        
        # Tensors
        tensor_list = []
        for name in self.tensor_info:
            tensor_list.append(self.tensor_to_json(name))
        
        handler_dict["weights"] = {
            "net" : None,
            "modules" : None, 
            "tensors" : tensor_list
        }

        # Activations
        acti_list = []
        for name in self.acti_info:
            acti_list.append(self.acti_to_json(name))
        
        handler_dict["activations"] = {
            "net" : None,
            "modules" : acti_list
        }
        return handler_dict    

    def tensor_to_json(self, tensor_name):
        """
        Creates a dict representing the tensor information to be later converted into json format
        """
        name = tensor_name
        tup = self.tensor_info[name]
        pert_list = tup[1]
        repr = tup[2]

        repr_data = repr.to_json() if repr is not None else None
        pert_data = [o.to_json() for o in pert_list] if pert_list is not None else None

        tensor_dict = {
            "name" : name,
            "repr" : repr_data,
            "perturb" : pert_data
        }

        return tensor_dict

    def acti_to_json(self, tensor_name):
        """
        Creates a dict representing the activation information to be later converted into json format
        """
        name = tensor_name
        tup = self.acti_info[name]
        pert_list = tup[0]
        repr = tup[1]

        repr_data = repr.to_json() if repr is not None else None
        pert_data = [o.to_json() for o in pert_list] if pert_list is not None else None

        acti_dict = {
            "name" : name,
            "repr" : repr_data,
            "perturb" : pert_data
        }

        return acti_dict