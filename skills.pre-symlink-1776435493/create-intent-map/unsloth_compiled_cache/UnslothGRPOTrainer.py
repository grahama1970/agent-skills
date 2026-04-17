"""
2026.1.4
2026.1.4
5.1.0
0.27.2
__UNSLOTH_VERSIONING__
"""

# Unsloth auto generated code
# Copyright 2023-present Daniel Han-Chen, Michael Han-Chen & the Unsloth team. All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from torch import Tensor
import torch
import torch.nn as nn
from torch.nn import functional as F
from typing import Any, List, Optional, Tuple, Union, Dict, Set, Callable
from trl.trainer.grpo_trainer import (Any, AutoModelForSequenceClassification, AutoProcessor, AutoTokenizer, BaseTrainer, Callable, DataLoader, Dataset, FSDP, GRPOConfig, GRPOTrainer, GenerationConfig, IterableDataset, Path, PeftConfig, PeftModel, PreTrainedModel, PreTrainedTokenizerBase, ProcessorMixin, RepeatSampler, RewardFunc, RolloutFunc, Sampler, SyncRefModelCallback, TrainerCallback, VLLMClient, Version, _ForwardRedirection, add_response_schema, apply_chat_template, asyncio, atexit, bnb, broadcast_object_list, copy, create_model_from_path, datasets, defaultdict, deque, disable_dropout_in_model, disable_gradient_checkpointing, ensure_master_addr_port, gather, gather_object, get_config_model_id, get_peft_model, get_training_chat_template, identity, inspect, is_bitsandbytes_available, is_conversational, is_datasets_available, is_jmespath_available, is_liger_kernel_available, is_peft_available, is_peft_model, is_rich_available, is_vllm_available, json, logger, nanmax, nanmin, nanstd, nn, nullcontext, os, pad, parse_response, partial, pd, prepare_deepspeed, prepare_fsdp, prepare_multimodal_messages, prepare_multimodal_messages_vllm, print_prompt_completions_sample, profiling_context, profiling_decorator, seed_worker, selective_log_softmax, set_seed, shuffle_sequence_dict, shutdown_event_loop_in_daemon, split_pixel_values_by_grid, split_tensor_dict, start_event_loop_in_daemon, sys, textwrap, time, torch, transformers, unsplit_pixel_values_by_grid, unwrap_model_for_generation, use_adapter, warnings, Any, apply_chat_template, copy, disable_gradient_checkpointing, gather, gather_object, nanmax, nanmin, nanstd, os, pad, pd, prepare_multimodal_messages, torch, use_adapter, FSDP, Version, apply_chat_template, broadcast_object_list, copy, gather, gather_object, is_conversational, json, nullcontext, os, pad, pd, prepare_multimodal_messages, prepare_multimodal_messages_vllm, profiling_context, time, torch, transformers, unwrap_model_for_generation, os, pad, selective_log_softmax, torch, transformers, Any, profiling_decorator, shuffle_sequence_dict, split_pixel_values_by_grid, split_tensor_dict, torch, unsplit_pixel_values_by_grid, PeftModel, PreTrainedModel, is_peft_available, logger, os, torch, FSDP, nn, os, pd, FSDP, is_peft_model, nn, pd, torch, GRPOTrainer, gather, os, pad, torch)


import os
from typing import *
from dataclasses import dataclass, field
from packaging.version import Version
import torch
import numpy as np
from contextlib import nullcontext
from torch.nn import functional as F
import inspect
from transformers import DataCollatorForSeq2Seq, DataCollatorForLanguageModeling as TransformersDataCollatorForLanguageModeling
from transformers.training_args import ParallelMode

# Wrap trainer with padding to right and enable training mode
# Also patches W&B since multiple runs must use wandb.finish()
import functools
from types import MethodType
try:
    from unsloth_zoo.gradient_checkpointing import reset_unsloth_gradient_checkpointing_buffers
except:
    def reset_unsloth_gradient_checkpointing_buffers(): pass
def prepare_for_training_mode(f):
    @functools.wraps(f)
    def wrapper(self, *args, **kwargs):
        # Enable training mode
        _was_training = None
        # Get gradient checkpointing setting from training arguments
        use_gc = getattr(self.args, 'gradient_checkpointing', True)
        if hasattr(self, 'model') and hasattr(self.model, "training"):
            _was_training = self.model.training
        if hasattr(self, 'model') and hasattr(self.model, "for_training"):
            self.model.for_training(use_gradient_checkpointing=use_gc)
        output = f(self, *args, **kwargs)
        # Restore previous mode when possible
        if hasattr(self, 'model') and hasattr(self.model, "for_inference"):
            if _was_training is False:
                self.model.for_inference()
            elif _was_training is True and hasattr(self.model, "for_training"):
                self.model.for_training(use_gradient_checkpointing=use_gc)
        # Reset gradient checkpointing buffers to free memory while staying ready for next run
        try:
            reset_unsloth_gradient_checkpointing_buffers()
        except:
            pass
        # Patch W&B to enable logging on future runs, otherwise it'll overwrite the first run
        try:
            import wandb
            wandb.finish()
        except:
            pass
        return output
    return wrapper
pass

torch_compile_options = {
    "epilogue_fusion"   : True,
    "max_autotune"      : False,
    "shape_padding"     : True,
    "trace.enabled"     : False,
    "triton.cudagraphs" : False,
}

@torch.compile(dynamic = True, fullgraph = True, options = torch_compile_options,)
def chunked_hidden_states_selective_log_softmax(
    hidden_states: torch.Tensor,
    lm_head: torch.Tensor,
    index: torch.Tensor,
    chunks: int = 4,
    logit_scale_multiply: float = 0.0,
    logit_scale_divide: float = 0.0,
    logit_softcapping: float = 0.0,
    temperature: float = 1.0,
) -> torch.Tensor:
    # All Unsloth Zoo code licensed under AGPL3 
    flat_hidden_states = hidden_states.reshape(-1, hidden_states.shape[-1]) 
    flat_index = index.reshape(-1)                                    

    chunked_hidden_states = torch.chunk(flat_hidden_states, chunks=chunks, dim=0)
    chunked_index = torch.chunk(flat_index, chunks=chunks, dim=0)
    
    all_per_token_logps = []
    
    for chunk_hidden_states, chunk_index in zip(chunked_hidden_states, chunked_index):
        chunk_logits = chunk_hidden_states.to(lm_head.dtype) @ lm_head.t()

        if logit_scale_multiply != 0.0:
            chunk_logits = chunk_logits * logit_scale_multiply
        if logit_scale_divide != 0.0:
            chunk_logits = chunk_logits / logit_scale_divide
        if logit_softcapping != 0.0:
            chunk_logits = chunk_logits * torch.tanh(chunk_logits / logit_softcapping)

        chunk_logits = chunk_logits.to(torch.float32)

        if temperature != 1.0:
            chunk_logits = chunk_logits / temperature

        selected_logits = torch.gather(chunk_logits, dim=-1, index=chunk_index.unsqueeze(-1)).squeeze(-1)
        logsumexp_values = torch.logsumexp(chunk_logits, dim=-1)
        per_token_logps = selected_logits - logsumexp_values
        all_per_token_logps.append(per_token_logps)
    
    all_per_token_logps = torch.concat(all_per_token_logps)
    
    all_per_token_logps = all_per_token_logps.reshape((hidden_states.shape[0], hidden_states.shape[1]))
    return all_per_token_logps

@torch.compile(dynamic = True, fullgraph = True, options = torch_compile_options,)
def chunked_selective_log_softmax(logits, index):
    # Split into 4 chunks only
    chunked_logits = torch.chunk(logits.reshape(-1, logits.shape[-1]), chunks = 4, dim = 0)
    chunked_index  = torch.chunk(index.reshape(-1), chunks = 4, dim = 0)
    all_per_token_logps = []
    # Below loop does the same as selective_log_softmax(chunk_logits, chunk_index)
    for chunk_logits, chunk_index in zip(chunked_logits, chunked_index):
        chunk_logits = chunk_logits.to(torch.float32)
        selected_logits = torch.gather(chunk_logits, dim = -1, index = chunk_index.unsqueeze(-1)).squeeze(-1)
        logsumexp_values = torch.logsumexp(chunk_logits, dim = -1)
        per_token_logps = selected_logits - logsumexp_values
        all_per_token_logps.append(per_token_logps)
    pass
    all_per_token_logps = torch.concat(all_per_token_logps)
    all_per_token_logps = all_per_token_logps.reshape((logits.shape[0], logits.shape[1]))
    return all_per_token_logps

def calculate_pad_tokens_in_prompt(
    input_ids: torch.Tensor,
    logits_to_keep: int,
    pad_token_id: int
) -> torch.Tensor:
    """
    Given prompt tensor, it returns all the left padded tokens in that sequence. so [pad, pad, pad, cat] = 3 tokens
    """
    if logits_to_keep >= input_ids.shape[1]:
        raise ValueError("logits_to_keep must be smaller than the sequence length.")

    prompt_section = input_ids[:, :-logits_to_keep]

    padding_mask = (prompt_section == pad_token_id)

    pad_token_counts = padding_mask.sum(dim=1)

    return pad_token_counts

def create_completion_attention_mask(
    completion_input_ids: torch.Tensor,
    left_pad_tokens_per_prompt: torch.Tensor,
    max_left_pad: int,
    pad_token_id: int
) -> torch.Tensor:
    """
    Given that we have a sequence, [p,p,p,c,c,c,pad,pad,pad]

    Where p are extra prompt tokens we got from slicing the torch tensor, c is completion tokens
    and pad are pad tokens, this function would make a completion mask that would 0 out the pad
    and p tokens. so in this example [0,0,0,1,1,1,0,0,0]
    """
    batch_size, completion_len = completion_input_ids.shape
    device = completion_input_ids.device

    num_tokens_to_mask = max_left_pad - left_pad_tokens_per_prompt

    indices = torch.arange(completion_len, device=device).unsqueeze(0)
    shift_mask = indices >= num_tokens_to_mask.unsqueeze(1)

    non_padding_mask = (completion_input_ids != pad_token_id)

    final_mask = shift_mask & non_padding_mask

    return final_mask

def left_pack_padding(tensor: torch.Tensor, pad_id: int) -> torch.Tensor:
    """
    Moves all padding tokens in each sequence of a batch to the right.
    """
    mask = (tensor != pad_id)
    # Must do stable=True since binary mark is unordered
    sorted_indices = torch.argsort(mask, dim=1, descending=True, stable=True)
    packed_tensor = torch.gather(tensor, 1, sorted_indices)
    return packed_tensor

def align_logprobs_with_mask(
    logprob_tensor: torch.Tensor,
    attention_mask: torch.Tensor,
    pad_value: float = 0.0
) -> torch.Tensor:
    """
    Aligns a log probability tensor with a given attention mask.
    """

    device = logprob_tensor.device
    batch_size, logprob_seq_len = logprob_tensor.shape
    mask_seq_len = attention_mask.shape[1]

    padded_logprobs = torch.full(
        attention_mask.shape,
        fill_value=pad_value,
        dtype=logprob_tensor.dtype,
        device=device
    )

    left_pad_counts = torch.argmax(attention_mask, dim=1)

    cols = torch.arange(logprob_seq_len, device=device)
    dest_indices = left_pad_counts.unsqueeze(1) + cols

    # Create destination row indices
    # Shape: [batch_size, logprob_seq_len]
    row_indices = torch.arange(batch_size, device=device).unsqueeze(1).expand_as(dest_indices)

    # --- 4. Filter out-of-bounds indices and perform assignment ---
    # Create a mask to identify only the indices that are within the bounds
    # of the target tensor's sequence length.
    valid_mask = dest_indices < mask_seq_len

    # Use this mask to select only the valid row indices, column indices,
    # and the corresponding values from the logprob tensor.
    # This flattens the selected elements into 1D tensors.
    valid_rows = row_indices[valid_mask]
    valid_cols = dest_indices[valid_mask]
    valid_vals = logprob_tensor[valid_mask]

    # Place the valid values into their correct positions in the padded tensor
    # using a single, efficient advanced indexing operation.
    padded_logprobs[valid_rows, valid_cols] = valid_vals

    return padded_logprobs

def autotune_batch_and_chunks(
    total_input_rows, 
    seq_len, 
    hidden_size, 
    vocab_size, 
    dtype_bytes=16,
    multiplier=None
):
    if multiplier is None:
        final_m = max(4, seq_len // 4096)
    else:
        final_m = multiplier
    
    if torch.cuda.is_available():
        free_bytes, _ = torch.cuda.mem_get_info()
        limit_gb = (free_bytes / (1024**3))*.80

    bytes_to_gb = 1024**3

    b_vals = torch.arange(total_input_rows, 0, -1, device='cpu', dtype=torch.float32)

    hidden_gb = (b_vals * seq_len * hidden_size * dtype_bytes) / bytes_to_gb

    base_logits = ((b_vals/total_input_rows) * b_vals * seq_len * vocab_size * dtype_bytes) / bytes_to_gb
    logits_gb = base_logits / final_m

    total_mem_gb = hidden_gb + logits_gb
    
    valid_mask = total_mem_gb <= limit_gb
    valid_indices = torch.nonzero(valid_mask, as_tuple=False)

    if valid_indices.shape[0] == 0:
        #This means your GPU will OOM
        return 4, final_m

    best_idx = valid_indices[0].item()
    final_b = int(b_vals[best_idx].item())

    return final_b, final_m
def grpo_compute_loss(
    ref,
    new,
    old,
    sampling_per_token_logps,
    input_ids,
    mask,
    beta,
    advantages,
    **kwargs
):
    # All Unsloth Zoo code licensed under AGPL3 
    # Set defaults for optional arguments
    loss_type = kwargs.get("loss_type", "grpo")
    epsilon_low = kwargs.get("epsilon_low", 0.2)
    epsilon_high = kwargs.get("epsilon_high", 0.2)
    max_completion_length = kwargs.get("max_completion_length", 8192)
    delta = kwargs.get("delta", None)
    importance_sampling_level = kwargs.get("importance_sampling_level", "token")
    num_items_in_batch = kwargs.get("num_items_in_batch", None)
    current_gradient_accumulation_steps = kwargs.get("current_gradient_accumulation_steps", 1)
    num_processes = kwargs.get("num_processes", 1)
    use_vllm = kwargs.get("use_vllm", False)
    vllm_importance_sampling_cap = kwargs.get("vllm_importance_sampling_cap", 2.0)
    input_ids = input_ids.unsqueeze(-1)

    with torch.no_grad():
        if use_vllm and sampling_per_token_logps is not None:
            #must filter out extra prompt tokens in begining after making input_ids left padded
            importance_sampling_ratio = torch.exp((old * mask) - sampling_per_token_logps)
            importance_sampling_ratio = torch.clamp(
                importance_sampling_ratio, max=vllm_importance_sampling_cap
            )
    pass

    # Reverse KL
    # Note that this is a low variance low bias estimator for the KL divergence as used in GRPO paper
    if beta != 0.0:
        kl_i = torch.exp(ref - new) - (ref - new) - 1.0

    else:
        # set kl_i to a tensor of zeros with the correct shape
        if importance_sampling_level == "sequence":
            kl_i = new.new_zeros(new.size(0), 1)
        else:
            kl_i = torch.zeros_like(new)
    # Full correct reverse KL divergence?? Missing term maybe?
    # kl_i = torch.exp(new) * kl_i

    # Below is forward KL (normal KL)
    # kl_i = torch.exp(old) * (old - new)
    if old is not None: 
        log_ratio = new - old
    else:
        log_ratio = new - new.detach()

    if importance_sampling_level == "token":
        log_importance_weights = log_ratio
    elif importance_sampling_level == "sequence":
        log_importance_weights = (log_ratio * mask).sum(-1) / mask.sum(-1).clamp(min=1.0)
        log_importance_weights = log_importance_weights.unsqueeze(-1)
    else:
        raise ValueError(
            f"Unknown importance sampling level: {importance_sampling_level}. Possible values are 'token' "
            "and 'sequence'."
        )

    coef_1 =  torch.exp(log_importance_weights)

    coef_2 = torch.clamp(coef_1, 1 - epsilon_low, 1 + epsilon_high)

    if delta is not None:
        loss_1 = torch.clamp(coef_1, max=delta) * advantages.unsqueeze(1)
    else:
        loss_1 = coef_1 * advantages.unsqueeze(1)
    pass

    # Must detach - otherwise gradients are not propagated correctly!
    # exp(x - x) == 1
    # loss_i = torch.exp(new - new.detach()) * advantages.unsqueeze(1)

    loss_2 = coef_2 * advantages.unsqueeze(1)
    loss_i = -torch.min(loss_1, loss_2)

    if use_vllm and sampling_per_token_logps is not None:
        loss_i = loss_i * importance_sampling_ratio
        #delta for metric
        with torch.no_grad():
            delta = torch.abs(old - sampling_per_token_logps)
            delta = delta * mask
            flat_is_ratio = importance_sampling_ratio * mask
    else:
        delta = torch.tensor([]).detach()
        flat_is_ratio = torch.tensor([]).detach()
    if beta != 0.0:
        loss_i = loss_i + beta * kl_i

    mask = mask.to(torch.float32)
    n_mask_per_reward = mask.sum(1)

    # https://github.com/huggingface/trl/blob/e8b8499f1f8d76838155b515e414ee98f757d6d5/trl/trainer/grpo_trainer.py#L1624
    if loss_type == "grpo":
        loss = ((loss_i * mask).sum(-1) / mask.sum(-1).clamp(min=1.0)).mean()
        loss = loss / current_gradient_accumulation_steps
    elif loss_type == "bnpo":
        loss = (loss_i * mask).sum() / mask.sum().clamp(min=1.0)
        loss = loss / current_gradient_accumulation_steps
    elif loss_type == "dr_grpo":
        loss = (loss_i * mask).sum() / (loss_i.size(0) * max_completion_length)
        loss = loss / current_gradient_accumulation_steps
    elif loss_type == "dapo":
        normalizer = num_items_in_batch/ num_processes
        loss = (loss_i * mask).sum() / normalizer
    else:
        raise ValueError(f"Unknown loss type: {loss_type}")

    # loss = (loss_i * mask).sum() / mask.sum()

    # Get metrics as well which are folded
    def masked_batch_mean(x):
        with torch.inference_mode():
            completion_length = n_mask_per_reward.mean()
            if x.shape[1] == 1:  # when importance_sampling_level == "sequence"
                return completion_length, x.mean()
            else:
                mean_kl_per_reward = (x * mask).sum(1) / n_mask_per_reward
                mean_kl = mean_kl_per_reward.mean()
                return completion_length, mean_kl
    completion_length, mean_kl = masked_batch_mean(kl_i)
    return loss, completion_length, mean_kl, delta, flat_is_ratio

class UnslothEfficientGRPO(torch.autograd.Function):
    # All Unsloth Zoo code licensed under AGPL3 
    @staticmethod
    def forward(ctx, _new_logps, _old_logps, _ref_logps, _sampling_per_token_logps, lm_head, _input_ids, _mask, _advantages, beta, scaler = None, n_chunks = 1, extra_kwargs=None):
        if extra_kwargs is None:
            extra_kwargs = {}
        def compute_loss(new_logps, old_logps, ref_logps, sampling_per_token_logps, input_ids, mask, advantages, scaling):
            loss, completion_length, mean_kl, delta, flat_is_ratio = grpo_compute_loss(
                ref_logps,
                new_logps,
                old_logps,
                sampling_per_token_logps,
                input_ids,
                mask,
                beta,
                advantages,
                **extra_kwargs,
            )

            # Scale loss if needed for mixed precision training
            scaled_loss = loss * scaling
            # Must add .loss.detach otherwise autograd uses 2x VRAM
            return scaled_loss, (loss.detach(), completion_length, mean_kl, delta, flat_is_ratio)
        pass

        device =_new_logps.device
        grad_inputs = torch.empty_like(_new_logps)
        accumulated_loss              = torch.zeros(1, device = device)
        accumulated_completion_length = torch.zeros(1, device = device)
        accumulated_mean_kl           = torch.zeros(1, device = device)
        accumulated_delta             = []
        accumulated_flat_is_ratio     = []

        def accumulate_chunk(
            new_logps_j,
            old_logps_j,
            ref_logps_j,
            sampling_per_token_logps_j,
            input_ids_j,
            mask_j,
            advantages_j,
            scaling,
            grad_inputs_j,
        ):
            (chunk_grad_input,), (chunk_loss, (unscaled_loss, chunk_completion_length, chunk_mean_kl, chunk_delta, chunk_flat_is_ratio)) = torch.func.grad_and_value(
                compute_loss,
                argnums = (0,),
                has_aux = True,
            )(new_logps_j, old_logps_j, ref_logps_j, sampling_per_token_logps_j, input_ids_j, mask_j, advantages_j, scaling)
            accumulated_loss             .add_(unscaled_loss)
            accumulated_completion_length.add_(chunk_completion_length)
            accumulated_mean_kl          .add_(chunk_mean_kl)
            accumulated_delta            .append(chunk_delta)
            accumulated_flat_is_ratio    .append(chunk_flat_is_ratio)
            grad_inputs_j[:] = chunk_grad_input
        pass

        accumulate_chunk = torch.compile(
            accumulate_chunk,
            fullgraph = True,
            # [TODO] Dynamic marking causes torch.compile errors if sequence length is long
            dynamic = True,
            options = torch_compile_options,
        )

        grad_inputs_chunks = torch.chunk(grad_inputs,        chunks = n_chunks, dim = 0)
        new_logps  = torch.chunk(_new_logps, chunks = n_chunks, dim = 0)
        if _old_logps is not None: 
            old_logps  = torch.chunk(_old_logps, chunks = n_chunks, dim = 0)
        else: 
            old_logps = [None] * n_chunks
        if _ref_logps is not None: 
            ref_logps  = torch.chunk(_ref_logps, chunks = n_chunks, dim = 0)
        else: 
            ref_logps = [None] * n_chunks
        if _sampling_per_token_logps is not None: 
            sampling_per_token_logps  = torch.chunk(_sampling_per_token_logps, chunks = n_chunks, dim = 0)
        else:
            sampling_per_token_logps = [None] * n_chunks
        input_ids          = torch.chunk(_input_ids,         chunks = n_chunks, dim = 0)
        mask               = torch.chunk(_mask,              chunks = n_chunks, dim = 0)
        advantages         = torch.chunk(_advantages,        chunks = n_chunks, dim = 0)

        # Get mixed precision scaling if seen
        scaling = scaler.get_scale() if scaler is not None else 1.0

        # Force torch.compile to use dynamic shapes for seqlen dim
        # mark_dynamic = lambda x: torch._dynamo.mark_dynamic(x, 1)

        for (grad_inputs_j, new_logps_j, old_logps_j, ref_logps_j, sampling_per_token_logps_j, input_ids_j, mask_j, advantages_j, ) in \
            zip(grad_inputs_chunks, new_logps, old_logps, ref_logps, sampling_per_token_logps, input_ids, mask, advantages):

            # [TODO] Dynamic marking causes torch.compile errors if sequence length is long

            # mark_dynamic(new_hidden_states_j)
            # mark_dynamic(ref_hidden_states_j)
            # if old_hidden_states_j is not None:
            #     mark_dynamic(old_hidden_states_j)
            # mark_dynamic(input_ids_j)
            # mark_dynamic(mask_j)
            accumulate_chunk(
                new_logps_j,
                old_logps_j,
                ref_logps_j,
                sampling_per_token_logps_j,
                input_ids_j,
                mask_j,
                advantages_j,
                scaling,
                grad_inputs_j,
            )
        pass

        grad_inputs                  .div_(n_chunks)
        accumulated_loss             .div_(n_chunks)
        accumulated_completion_length.div_(n_chunks)
        accumulated_mean_kl          .div_(n_chunks)

        if _sampling_per_token_logps is not None:
            accumulated_delta = torch.cat(accumulated_delta, dim=0)
            accumulated_flat_is_ratio = torch.cat(accumulated_flat_is_ratio, dim=0)
        else:
            accumulated_delta = None
            accumulated_flat_is_ratio = None
        ctx.save_for_backward(grad_inputs)
        return (
            accumulated_loss,
            accumulated_completion_length,
            accumulated_mean_kl,
            accumulated_delta,
            accumulated_flat_is_ratio
        )
    pass

    @staticmethod
    def backward(ctx, grad_output, dcompletion_length, dmean_kl, ddelta, ddflat_is_ratio):
        (grad_input,) = ctx.saved_tensors
        return (grad_input, None, None, None, None, None, None, None, None, None, None, None)
    pass

def grpo_accumulated_loss(
    trainer,
    input_ids,
    attention_mask,
    logits_to_keep,
    completion_mask,
    advantages,
    old_logps,
    ref_logps, 
    n_chunks = -1,
    **kwargs,
):
    # All Unsloth Zoo code licensed under AGPL3 
    bsz, qlen = input_ids.shape

    pixel_values = kwargs.get('pixel_values',None)
    image_grid_thw = kwargs.get('image_grid_thw',None)
    pixel_attention_mask = kwargs.get('pixel_attention_mask',None)
    image_sizes = kwargs.get('image_sizes',None)
    sampling_per_token_logps = kwargs.get("sampling_per_token_logps", None) if getattr(trainer, "vllm_importance_sampling_correction", False) else None
    temperature = kwargs.get("temperature", 1.0)
    logit_scale_multiply = kwargs.get("logit_scale_multiply", 0.0)
    logit_scale_divide   = kwargs.get("logit_scale_divide", 0.0)
    logit_softcapping    = kwargs.get("logit_softcapping", 0.0)
    prev_max_left_pad    = kwargs.get("max_left_pad", 0) #Always get max_left_pad for when training LLMs, enabled by deafult.  

    #Delete this from kwargs so less issues 
    _ = kwargs.pop("sampling_per_token_logps", None)
    kwargs["vllm_importance_sampling_cap"] = trainer.vllm_importance_sampling_cap if sampling_per_token_logps is not None else None
    kwargs["use_vllm"] = trainer.use_vllm
    # Find closest multiple
    factors = [i for i in range(1, bsz + 1) if bsz % i == 0]
    if n_chunks == -1: n_chunks = bsz
    n_chunks = factors[min(np.searchsorted(factors, n_chunks), len(factors)-1)]

    if not hasattr(trainer, '_autocast_dtype'):
        trainer._autocast_dtype = torch.float16 if os.environ.get('ACCELERATE_MIXED_PRECISION', 'fp16') == 'fp16' else torch.bfloat16
        if os.environ.get('UNSLOTH_FORCE_FLOAT32', '0') == '1': trainer._autocast_dtype = None
    pass
    os.environ["UNSLOTH_RETURN_HIDDEN_STATES"] = "1"

    lm_head = trainer.model.get_output_embeddings().weight
    dtype_bytes = 16 if trainer._autocast_dtype in [torch.float16, torch.bfloat16] else 32

    total_rows = input_ids.shape[0]
    seq_len = input_ids.shape[1]
    hidden_dim = lm_head.shape[1]
    vocab_dim = lm_head.shape[0]
    
    if trainer.args.unsloth_grpo_mini_batch is None: 
        if not hasattr(trainer, "_has_autotuned"):
            trainer._has_autotuned = True
            B, multiplier = autotune_batch_and_chunks(
                total_rows, seq_len, hidden_dim, vocab_dim, dtype_bytes, trainer.args.unsloth_logit_chunk_multiplier
            )
            trainer.args.unsloth_grpo_mini_batch = total_rows//B 
            trainer.args.unsloth_logit_chunk_multiplier = multiplier
            B = trainer.args.unsloth_grpo_mini_batch
            multiplier = trainer.args.unsloth_logit_chunk_multiplier
        elif trainer._step % trainer.current_gradient_accumulation_steps == 0:
            B = trainer.args.unsloth_grpo_mini_batch
            multiplier = trainer.args.unsloth_logit_chunk_multiplier
            del trainer._has_autotuned
            del trainer.args.unsloth_grpo_mini_batch
            del trainer.args.unsloth_logit_chunk_multiplier 
        else:
            B = trainer.unsloth_grpo_mini_batch
            multiplier = trainer.args.unsloth_logit_chunk_multiplier
    else: 
        if trainer.args.unsloth_grpo_mini_batch > total_rows: 
            B = total_rows
        else:
            B = trainer.args.unsloth_grpo_mini_batch

        if trainer.args.unsloth_logit_chunk_multiplier is None:
            multiplier = max(4, seq_len // 4096)
        else: 
            multiplier = trainer.args.unsloth_logit_chunk_multiplier
        
    if pixel_values is None:
        left_pad_tokens_per_prompt = calculate_pad_tokens_in_prompt(input_ids, logits_to_keep, trainer.processing_class.pad_token_id)

        # Determine max_left_pad from precomputed logprobs shape for consistency
        if old_logps is not None:
            max_left_pad = old_logps.shape[1] - logits_to_keep
        elif ref_logps is not None:
            max_left_pad = ref_logps.shape[1] - logits_to_keep
        else:
            max_left_pad = torch.max(left_pad_tokens_per_prompt).item()

        input_ids = left_pack_padding(input_ids, trainer.processing_class.pad_token_id)

        completion_input_ids = input_ids[:, -(logits_to_keep +max_left_pad):]

        completion_mask = create_completion_attention_mask(completion_input_ids, left_pad_tokens_per_prompt, max_left_pad, trainer.processing_class.pad_token_id).to(attention_mask.dtype)

        if trainer.use_vllm and sampling_per_token_logps is not None and getattr(trainer, "vllm_importance_sampling_correction", False):
            sampling_per_token_logps = align_logprobs_with_mask(sampling_per_token_logps, completion_mask)
        else: 
            sampling_per_token_logps = None
        attention_mask =  input_ids != trainer.processing_class.pad_token_id
        attention_mask = attention_mask.to(attention_mask.dtype)
    else:
        completion_input_ids = input_ids[:, -logits_to_keep:]

    unwrapped_model = trainer.accelerator.unwrap_model(trainer.model, keep_fp32_wrapper = False)

    for module in unwrapped_model.modules():
        if hasattr(module, "_hf_hook") and hasattr(module._hf_hook, "io_same_decice"):
            module._hf_hook.io_same_decice = False
    pass

    all_logprobs_list = []

    attention_mask_chunks = torch.chunk(attention_mask, chunks=B, dim=0)
    completion_ids_chunks = torch.chunk(completion_input_ids, chunks=B, dim=0)

    def chunk_optional(tensor, chunks):
        if tensor is None:
            return [None] * chunks
        return torch.chunk(tensor, chunks=chunks, dim=0)

    import math
    total_samples = input_ids.shape[0]
    batch_size = math.ceil(total_samples / B)

    input_ids_chunks = []
    attention_mask_chunks = []
    pixel_values_chunks = []
    image_grid_thw_chunks = []
    pixel_attention_mask_chunks = []

    current_pixel_idx = 0
    #TRL 0.23.0 batching logic
    for start in range(0, total_samples, batch_size):
        end = start + batch_size
        
        input_ids_chunks.append(input_ids[start:end])
        attention_mask_chunks.append(attention_mask[start:end])

        if image_grid_thw is not None and pixel_values is not None:
            
            grid_slice = image_grid_thw[start:end]
            image_grid_thw_chunks.append(grid_slice)
            

            batch_pixel_count = grid_slice.prod(dim=-1).sum().item()
            
            start_pixel_idx = current_pixel_idx
            end_pixel_idx = current_pixel_idx + batch_pixel_count
            
            pixel_values_chunks.append(pixel_values[start_pixel_idx:end_pixel_idx])
            
            if pixel_attention_mask is not None:
                pixel_attention_mask_chunks.append(
                    pixel_attention_mask[start_pixel_idx:end_pixel_idx]
                )
            else:
                pixel_attention_mask_chunks.append(None)
            
            current_pixel_idx = end_pixel_idx
            
        else:
            pixel_values_chunks.append(None)
            image_grid_thw_chunks.append(None)
            pixel_attention_mask_chunks.append(None)
    
    if image_sizes is not None and not isinstance(image_sizes, torch.Tensor):
        image_sizes_chunks = [[size] for size in image_sizes]
    else:
        image_sizes_chunks = chunk_optional(image_sizes, B)

    zipped_inputs = zip(
        input_ids_chunks,
        attention_mask_chunks,
        pixel_values_chunks,
        image_grid_thw_chunks,
        pixel_attention_mask_chunks,
        image_sizes_chunks,
        completion_ids_chunks 
    )

    if trainer._autocast_dtype is None:
        autocaster = nullcontext()
    else:
        autocaster = torch.amp.autocast(device_type = trainer.model.device.type, dtype = trainer._autocast_dtype)

    def to_device(tensor, device, non_blocking=True):
        if tensor is None: return None
        return tensor.to(device, non_blocking=non_blocking)

    class Unsloth_Offloaded_Log_Softmax(torch.autograd.Function):
        """
        Manual Gradient Checkpointing/CPU Offloading for Log Softmax.
        """
        @staticmethod
        def forward(ctx, hidden_states, lm_head, index, chunks, 
                    logit_scale_multiply, logit_scale_divide, 
                    logit_softcapping, temperature):
            
            ctx.saved_hidden_states = to_device(hidden_states, "cpu", non_blocking=True)
            ctx.device = hidden_states.device
            ctx.dtype = hidden_states.dtype
            
            ctx.lm_head = lm_head
            ctx.lm_head_requires_grad = lm_head.requires_grad
            ctx.index = index
            ctx.args = (chunks, logit_scale_multiply, logit_scale_divide, logit_softcapping, temperature)
            
            with torch.no_grad():
                output = chunked_hidden_states_selective_log_softmax(
                    hidden_states, lm_head, index, *ctx.args
                )
                
            return output

        @staticmethod
        def backward(ctx, grad_output):
            hidden_states = to_device(ctx.saved_hidden_states, ctx.device)
            hidden_states = hidden_states.to(ctx.dtype)
            hidden_states.requires_grad_(True)
            
            lm_head = ctx.lm_head
            # #Possibly redundant lines
            # if ctx.lm_head_requires_grad:
            #     hidden_states.requires_grad_(True)
            # else: 
            #     lm_head = lm_head.detach()
            
            index = ctx.index
            
            with torch.enable_grad():
                output = chunked_hidden_states_selective_log_softmax(
                    hidden_states, lm_head, index, *ctx.args
                )
                
            torch.autograd.backward(output, grad_output)

            return (
                hidden_states.grad,  
                lm_head.grad if ctx.lm_head_requires_grad else None,        
                None,                
                None,                
                None,                
                None,                
                None,               
                None,                
            )

    def efficient_log_softmax(hidden_states, lm_head, index, chunks=32, 
                            logit_scale_multiply=0.0, logit_scale_divide=0.0, 
                            logit_softcapping=0.0, temperature=1, batch_size=8):
        if (index.shape[1] <= 1024 and batch_size <= 8) or batch_size==1:
            #We save a gigabyte or speed with the normal path under these specific conditions
            return chunked_hidden_states_selective_log_softmax(
                hidden_states,
                lm_head,
                index,
                chunks, 
                logit_scale_multiply, 
                logit_scale_divide,
                logit_softcapping, 
                temperature
            )
        else: 
            return Unsloth_Offloaded_Log_Softmax.apply(
                hidden_states, lm_head, index, chunks, 
                logit_scale_multiply, logit_scale_divide, 
                logit_softcapping, temperature
            )
    
    
    for (
        input_ids_chunk,
        attention_mask_chunk,
        pixel_values_chunk,
        image_grid_thw_chunk,
        pixel_attention_mask_chunk,
        image_sizes_chunk,
        completion_ids 
    ) in zipped_inputs:
            with autocaster:
                if pixel_values is None:
                    new_hidden_states_chunk = unwrapped_model(
                        input_ids = input_ids_chunk,
                        attention_mask = attention_mask_chunk,
                        pixel_values = pixel_values_chunk,
                        image_grid_thw = image_grid_thw_chunk,
                        pixel_attention_mask = pixel_attention_mask_chunk,
                        image_sizes = image_sizes_chunk,
                    ).logits
                    
                    new_hidden_states_chunk = new_hidden_states_chunk[:, -(logits_to_keep + max_left_pad + 1): , :]
                    new_hidden_states_chunk = new_hidden_states_chunk[:, :-1, :]
                else: 
                    new_hidden_states_chunk = unwrapped_model(
                        input_ids = input_ids_chunk,
                        attention_mask = attention_mask_chunk,
                        pixel_values = pixel_values_chunk,
                        image_grid_thw = image_grid_thw_chunk,
                        pixel_attention_mask = pixel_attention_mask_chunk,
                        image_sizes = image_sizes_chunk,
                        logits_to_keep = logits_to_keep + 1, 
                    ).logits
                    
                    new_hidden_states_chunk = new_hidden_states_chunk[:, :-1, :]

                logprobs_chunk = efficient_log_softmax(
                    new_hidden_states_chunk, 
                    lm_head, 
                    completion_ids, 
                    chunks=input_ids_chunk.shape[0]*multiplier, 
                    logit_scale_multiply=logit_scale_multiply,
                    logit_scale_divide=logit_scale_divide,
                    logit_softcapping=logit_softcapping,
                    temperature=temperature,
                    batch_size = B
                )
                #This is needed to avoid race conditions with GPT OSS offload_embbed=True
                #However, it seems that this line does not slow down or disrupt models. 
                torch.cuda.synchronize()
            all_logprobs_list.append(logprobs_chunk)

    new_logprobs = torch.cat(all_logprobs_list, dim=0)
    
    with autocaster:
        loss, completion_length, mean_kl, delta, flat_is_ratio = UnslothEfficientGRPO.apply(
            new_logprobs,
            old_logps,
            ref_logps,
            sampling_per_token_logps,
            lm_head,
            completion_input_ids,
            completion_mask,
            advantages,
            trainer.beta,
            trainer.accelerator.scaler,
            n_chunks,
            kwargs 
        )

    # Must force not returning hidden states but logits otherwise gibberish
    os.environ["UNSLOTH_RETURN_HIDDEN_STATES"] = "0"

    return loss, completion_length, mean_kl, delta, flat_is_ratio
    # Old non efficient code path
    new_logits = torch.matmul(new_hidden_states, lm_head.t())
    new_logits = new_logits[:, :-1, :] # exclude the last logit: it corresponds to the next token pred
    old_logits = torch.matmul(old_hidden_states, lm_head.t())
    old_logits = old_logits[:, :-1, :] # exclude the last logit: it corresponds to the next token pred
    loss, completion_length, mean_kl = grpo_compute_loss(
        old_logits,
        new_logits,
        completion_input_ids,
        completion_mask,
        trainer.beta,
        advantages,
    )
    return loss, completion_length, mean_kl
    pass

@torch.compile(dynamic = True, fullgraph = True, options = torch_compile_options)
def grpo_compute_loss_slow(
    ref,
    new,
    old,
    sampling_per_token_logps,
    input_ids,
    mask,
    beta,
    advantages,
    **kwargs
):
    # All Unsloth Zoo code licensed under AGPL3 
    # Set defaults for optional arguments
    loss_type = kwargs.get("loss_type", "grpo")
    epsilon_low = kwargs.get("epsilon_low", 0.2)
    epsilon_high = kwargs.get("epsilon_high", 0.2)
    max_completion_length = kwargs.get("max_completion_length", 8192)
    delta = kwargs.get("delta", None)
    importance_sampling_level = kwargs.get("importance_sampling_level", "token")
    num_items_in_batch = kwargs.get("num_items_in_batch", None)
    current_gradient_accumulation_steps = kwargs.get("current_gradient_accumulation_steps", 1)
    num_processes = kwargs.get("num_processes", 1)
    use_vllm = kwargs.get("use_vllm", False)
    vllm_importance_sampling_cap = kwargs.get("vllm_importance_sampling_cap", 2.0)
    input_ids = input_ids.unsqueeze(-1)

    with torch.no_grad():
        if use_vllm and sampling_per_token_logps is not None:
            #must filter out extra prompt tokens in begining after making input_ids left padded
            importance_sampling_ratio = torch.exp((old * mask) - sampling_per_token_logps)
            importance_sampling_ratio = torch.clamp(
                importance_sampling_ratio, max=vllm_importance_sampling_cap
            )
    pass

    # Reverse KL
    # Note that this is a low variance low bias estimator for the KL divergence as used in GRPO paper
    if beta != 0.0:
        kl_i = torch.exp(ref - new) - (ref - new) - 1.0

    else:
        # set kl_i to a tensor of zeros with the correct shape
        if importance_sampling_level == "sequence":
            kl_i = new.new_zeros(new.size(0), 1)
        else:
            kl_i = torch.zeros_like(new)
    # Full correct reverse KL divergence?? Missing term maybe?
    # kl_i = torch.exp(new) * kl_i

    # Below is forward KL (normal KL)
    # kl_i = torch.exp(old) * (old - new)
    if old is not None: 
        log_ratio = new - old
    else:
        log_ratio = new - new.detach()

    if importance_sampling_level == "token":
        log_importance_weights = log_ratio
    elif importance_sampling_level == "sequence":
        log_importance_weights = (log_ratio * mask).sum(-1) / mask.sum(-1).clamp(min=1.0)
        log_importance_weights = log_importance_weights.unsqueeze(-1)
    else:
        raise ValueError(
            f"Unknown importance sampling level: {importance_sampling_level}. Possible values are 'token' "
            "and 'sequence'."
        )

    coef_1 =  torch.exp(log_importance_weights)

    coef_2 = torch.clamp(coef_1, 1 - epsilon_low, 1 + epsilon_high)

    if delta is not None:
        loss_1 = torch.clamp(coef_1, max=delta) * advantages.unsqueeze(1)
    else:
        loss_1 = coef_1 * advantages.unsqueeze(1)
    pass

    # Must detach - otherwise gradients are not propagated correctly!
    # exp(x - x) == 1
    # loss_i = torch.exp(new - new.detach()) * advantages.unsqueeze(1)

    loss_2 = coef_2 * advantages.unsqueeze(1)
    loss_i = -torch.min(loss_1, loss_2)

    if use_vllm and sampling_per_token_logps is not None:
        loss_i = loss_i * importance_sampling_ratio
        #delta for metric
        with torch.no_grad():
            delta = torch.abs(old - sampling_per_token_logps)
            delta = delta * mask
            flat_is_ratio = importance_sampling_ratio * mask
    else:
        delta = torch.tensor([]).detach()
        flat_is_ratio = torch.tensor([]).detach()
    if beta != 0.0:
        loss_i = loss_i + beta * kl_i

    mask = mask.to(torch.float32)
    n_mask_per_reward = mask.sum(1)

    # https://github.com/huggingface/trl/blob/e8b8499f1f8d76838155b515e414ee98f757d6d5/trl/trainer/grpo_trainer.py#L1624
    if loss_type == "grpo":
        loss = ((loss_i * mask).sum(-1) / mask.sum(-1).clamp(min=1.0)).mean()
        loss = loss / current_gradient_accumulation_steps
    elif loss_type == "bnpo":
        loss = (loss_i * mask).sum() / mask.sum().clamp(min=1.0)
        loss = loss / current_gradient_accumulation_steps
    elif loss_type == "dr_grpo":
        loss = (loss_i * mask).sum() / (loss_i.size(0) * max_completion_length)
        loss = loss / current_gradient_accumulation_steps
    elif loss_type == "dapo":
        normalizer = num_items_in_batch/ num_processes
        loss = (loss_i * mask).sum() / normalizer
    else:
        raise ValueError(f"Unknown loss type: {loss_type}")

    # loss = (loss_i * mask).sum() / mask.sum()

    # Get metrics as well which are folded
    def masked_batch_mean(x):
        with torch.inference_mode():
            completion_length = n_mask_per_reward.mean()
            if x.shape[1] == 1:  # when importance_sampling_level == "sequence"
                return completion_length, x.mean()
            else:
                mean_kl_per_reward = (x * mask).sum(1) / n_mask_per_reward
                mean_kl = mean_kl_per_reward.mean()
                return completion_length, mean_kl
    completion_length, mean_kl = masked_batch_mean(kl_i)
    return loss, completion_length, mean_kl, delta, flat_is_ratio

def grpo_update_SamplingParams(SamplingParams, generation_kwargs, vllm_sampling_params = None):
    good_sampling_params_keys = inspect.signature(SamplingParams).parameters.keys()

    # Filter generation_kwargs
    new_generation_kwargs = {}
    for key in generation_kwargs.keys():
        if key in good_sampling_params_keys:
            new_generation_kwargs[key] = generation_kwargs[key]
    generation_kwargs = new_generation_kwargs

    if vllm_sampling_params is not None:
        for key in good_sampling_params_keys:
            if hasattr(vllm_sampling_params, key):
                overwrited_key = getattr(vllm_sampling_params, key)
                if overwrited_key is not None and (type(overwrited_key) in (list, tuple,) and len(overwrited_key) != 0):
                    generation_kwargs[key] = overwrited_key
    return generation_kwargs

def _get_inference_mode_context_manager(model: torch.nn.Module):
    """
    If the state dict was quantized using torchao, we will run into
    the following error when calling ops like aten.t() in inference mode.
    This is a bug in PyTorch that affects all tensor subclasses.

        Cannot set version_counter for inference tensor

    For now, we work around this issue by using `torch.no_grad()` in this case.
    See https://github.com/pytorch/pytorch/issues/164872 for more details.
    Otherwise, just return `torch.inference_mode()`.
    """
    torchao_config = getattr(model, "torchao_config", None)
    if torchao_config is not None and torchao_config.qat_scheme is None:
        return torch.no_grad()
    else:
        return torch.inference_mode()

def vLLMSamplingParams(**kwargs):
    from vllm import SamplingParams

    sampling_params = SamplingParams(**kwargs)
    sampling_params._set_kwargs = kwargs
    return sampling_params
@dataclass
class UnslothGRPOConfig(GRPOConfig):
    """
    
Configuration class for the [`GRPOTrainer`].

This class includes only the parameters that are specific to GRPO training. For a full list of training arguments,
please refer to the [`~transformers.TrainingArguments`] documentation. Note that default values in this class may
differ from those in [`~transformers.TrainingArguments`].

Using [`~transformers.HfArgumentParser`] we can turn this class into
[argparse](https://docs.python.org/3/library/argparse#module-argparse) arguments that can be specified on the
command line.

Parameters:
    > Parameters that control the model and reference model

    model_init_kwargs (`str`, `dict[str, Any]`, *optional*):
        Keyword arguments for [`~transformers.AutoModelForCausalLM.from_pretrained`], used when the `model`
        argument of the [`GRPOTrainer`] is provided as a string.
    disable_dropout (`bool`, *optional*, defaults to `False`):
        Whether to disable dropout in the model. This is useful for training with a reference model, as it prevents
        the model from generating different logprobs for the same input.
    cast_lm_head_to_fp32 (`bool`, *optional*, defaults to `False`):
        Whether to cast the language modeling head of the policy and reference models to float32. As recommended by
        the [ScaleRL](https://huggingface.co/papers/2510.13786) recipe. This flag is only supported when the model
        has untied word embedding and language modeling head layers i.e. `tie_word_embeddings` in the model config
        is False.

    > Parameters that control the data preprocessing

    remove_unused_columns (`bool`, *optional*, defaults to `False`):
        Whether to only keep the column `"prompt"` in the dataset. If you use a custom reward function that
        requires any column other than `"prompts"` and `"completions"`, you should keep this to `False`.
    num_generations (`int`, *optional*, defaults to `8`):
        Number of generations per prompt to sample. The effective batch size (num_processes * per_device_batch_size
        * gradient_accumulation_steps) must be evenly divisible by this value.
    num_generations_eval (`int` or `None`, *optional*):
        Number of generations to sample during evaluation. This allows using fewer generations during evaluation to
        save computation. If `None`, uses the value of `num_generations`.
    max_completion_length (`int` or `None`, *optional*, defaults to `256`):
        Maximum length of the generated completion.
    ds3_gather_for_generation (`bool`, *optional*, defaults to `True`):
        This setting applies to DeepSpeed ZeRO-3. If enabled, the policy model weights are gathered for generation,
        improving generation speed. However, disabling this option allows training models that exceed the VRAM
        capacity of a single GPU, albeit at the cost of slower generation. Disabling this option is not compatible
        with vLLM generation.
    shuffle_dataset (`bool`, *optional*, defaults to `True`):
        Whether to shuffle the training dataset.

    > Parameters that control generation

    generation_batch_size: (`int`, *optional*):
        Batch size to use for generation. If `None`, it defaults to the effective training batch size:
        `per_device_train_batch_size * num_processes * steps_per_generation`. In other words, there is one
        generation batch processed per optimization step. Mutually exclusive with `steps_per_generation`.
    steps_per_generation: (`int`, *optional*):
        Number of steps per generation. If `None`, it defaults to `gradient_accumulation_steps`. Mutually exclusive
        with `generation_batch_size`.
    temperature (`float`, defaults to `1.0`):
        Temperature for sampling. The higher the temperature, the more random the completions.
    top_p (`float`, *optional*, defaults to `1.0`):
        Float that controls the cumulative probability of the top tokens to consider. Must be in (0, 1]. Set to
        `1.0` to consider all tokens.
    top_k (`int`, *optional*, defaults to `0`):
        Number of highest probability vocabulary tokens to keep for top-k-filtering. If `0`, top-k-filtering is
        disabled and all tokens are considered.
    min_p (`float`, *optional*):
        Minimum token probability, which will be scaled by the probability of the most likely token. It must be a
        value between `0.0` and `1.0`. Typical values are in the `0.01-0.2` range.
    generation_kwargs (`dict[str, Any]`, *optional*):
        Additional keyword arguments to pass to [`~transformers.GenerationConfig`] (if using transformers) or
        `SamplingParams` (if using vLLM) when sampling completions. This can be used to further customize the
        generation behavior, such as setting `suppress_tokens`, `num_beams`, etc. If it contains keys that conflict
        with the other generation parameters (like `min_p`, `top_p`, etc.), they will override them.
    chat_template_kwargs (`dict[str, Any]`, *optional*):
        Additional keyword arguments to pass to the `apply_chat_template` function when generating completions.
    repetition_penalty (`float`, *optional*, defaults to `1.0`):
        Float that penalizes new tokens based on whether they appear in the prompt and the generated text so far.
        Values > `1.0` encourage the model to use new tokens, while values < `1.0` encourage the model to repeat
        tokens.
    use_transformers_paged (`bool`, *optional*, defaults to `False`):
        Whether to use the `transformers` paged implementation for generation. If set to `True`, the `transformers`
        paged implementation will be used for generation instead of the default padded implementation. This
        parameter is only effective when `use_vllm` is set to `False`.
    cache_implementation (`str`, *optional*):
        Implementation of the cache method for faster generation when `use_vllm` is set to `False`.

    > Parameters that control generation acceleration powered by vLLM

    use_vllm (`bool`, *optional*, defaults to `False`):
        Whether to use vLLM for generating completions. If set to `True`, the trainer will use vLLM for generation
        instead of the default model.generate(). Requires `vllm` to be installed.
    vllm_mode (`str`, *optional*, defaults to `"server"`):
        Mode to use for vLLM integration when `use_vllm` is set to `True`. Must be one of `"server"` or
        `"colocate"`.

        - `"server"`: The trainer will send generation requests to a separate vLLM server. Make sure a TRL vLLM
          server is running (start with `trl vllm-serve`).
        - `"colocate"`: vLLM will run in the same process and share the training GPUs. This avoids the need for a
          separate server but may cause resource contention with training.
    vllm_model_impl (`str`, *optional*, defaults to `"vllm"`):
        Model implementation to use for vLLM. Must be one of `"transformers"` or `"vllm"`. `"transformers"`: Use
        the `transformers` backend for model implementation. `"vllm"`: Use the `vllm` library for model
        implementation.
    vllm_structured_outputs_regex (`str`, *optional*):
        Regex for vLLM structured outputs. If `None` (default), structured outputs is disabled.

    > Parameters that control the vLLM server (only used when `vllm_mode` is `"server"`)

    vllm_server_base_url (`str`, *optional*):
        Base URL for the vLLM server (e.g., `"http://localhost:8000"`). If provided, `vllm_server_host` and
        `vllm_server_port` are ignored.
    vllm_server_host (`str`, *optional*, defaults to `"0.0.0.0"`):
        Host of the vLLM server to connect to. Ignored if `vllm_server_base_url` is provided.
    vllm_server_port (`int`, *optional*, defaults to `8000`):
        Port of the vLLM server to connect to. Ignored if `vllm_server_base_url` is provided.
    vllm_server_timeout (`float`, *optional*, defaults to `240.0`):
        Total timeout duration in seconds to wait for the vLLM server to be up. If the server is not up after the
        timeout, a `ConnectionError` is raised.
    vllm_group_port (`int`, *optional*, defaults to `51216`):
        Port number for the weight update group. This is used to communicate with the vLLM server. Unless the port
        is occupied, there is no need to change it.

    > Parameters that control colocated vLLM execution (only used when `vllm_mode` is `"colocate"`)

    vllm_gpu_memory_utilization (`float`, *optional*, defaults to `0.3`):
        Control the GPU memory utilization for vLLM. This setting only applies when `vllm_mode` is set to
        `"colocate"`. If you are using `vllm_mode="server"`, this parameter must be passed separately when
        launching the vLLM server via the `--vllm_gpu_memory_utilization` flag.
    vllm_max_model_length (`int`, *optional*):
        Context window for vLLM. Set it to at least the maximum prompt length in the dataset plus
        `max_completion_length`; if omitted, it is inferred from the model config.
    vllm_tensor_parallel_size (`int`, *optional*, defaults to `1`):
        Control the tensor parallel size for vLLM. This setting only applies when `vllm_mode` is set to
        `"colocate"`. If you are using `vllm_mode="server"`, this parameter must be passed separately when
        launching the vLLM server via the `--vllm_tensor_parallel_size` flag.
    vllm_enable_sleep_mode (`bool`, *optional*, defaults to `False`):
        Enable vLLM sleep mode to offload weights/cache during the optimizer step. Keeps GPU memory usage low, but
        waking the engine adds host–device transfer latency.

    > Parameters that control the training

    beta (`float`, *optional*, defaults to `0.0`):
        KL coefficient. If `0.0` (default), the reference model is not loaded, reducing memory usage and improving
        training speed. [DeepSeek-R1 incentivizes reasoning in LLMs through reinforcement
        learning](https://huggingface.co/papers/2501.12948) use a value of `0.001`.
    num_iterations (`int`, *optional*, defaults to `1`):
        Number of iterations per batch (denoted as μ in the algorithm).
    epsilon (`float`, *optional*, defaults to `0.2`):
        Epsilon value for clipping.
    delta (`float`, *optional*):
        Enables the upper clipping bound in two-sided GRPO loss when set to a float. If `None` (default), standard
        GRPO clipping is used. Recommended to be greater than `1 + ε` when enabled. This method is introduced in
        the [INTELLECT-2 tech report](https://huggingface.co/papers/2505.07291).
    epsilon_high (`float`, *optional*):
        Upper-bound epsilon value for clipping. If not specified, it defaults to the same value as the lower-bound
        specified in argument `epsilon`. Paper [DAPO](https://huggingface.co/papers/2503.14476) recommends `0.28`.
        When used with `loss_type='cispo'`, this corresponds to the ε_max param specified in the [ScaleRL
        paper](https://huggingface.co/papers/2510.13786) and the recommended value is `5.0`.
    sapo_temperature_neg (`float`, *optional*, defaults to `1.05`):
        Temperature for tokens with non-positive advantage scores used in the `sapo` loss function. This parameter
        is introduced in the [Soft Adaptive Policy Optimization paper](https://huggingface.co/papers/2511.20347).
    sapo_temperature_pos (`float`, *optional*, defaults to `1.0`):
        Temperature for tokens with positive advantage scores used in the `sapo` loss function. This parameter is
        introduced in the [Soft Adaptive Policy Optimization paper](https://huggingface.co/papers/2511.20347).
    importance_sampling_level (`str`, *optional*, defaults to `"token"`):
        Controls whether importance sampling ratios are computed at the `"token"` or `"sequence"` level. `"token"`
        keeps the raw per-token log-probability ratios (one weight per token). `"sequence"` averages the
        log-probability ratios across valid tokens to produce a single ratio per sequence. The [GSPO
        paper](https://huggingface.co/papers/2507.18071) shows that sequence-level sampling often yields more
        stable training and better alignment with sequence-level rewards.
    reward_weights (`list[float]`, *optional*):
        Weights for each reward function. Must match the number of reward functions. If `None`, all rewards are
        weighted equally with weight `1.0`.
    multi_objective_aggregation (`str`, *optional*, defaults to `"sum_then_normalize"`):
        Method to aggregate multiple reward functions. Supported values are:

        - `"sum_then_normalize"` (default): First sums the weighted rewards from each reward function, then applies
          reward scaling/normalization as specified by `scale_rewards` (see `scale_rewards` for details).
        - `"normalize_then_sum"`: First normalizes/scales each reward function across generations (within each
          group), then sums the normalized rewards using the specified weights. The aggregated reward is then
          normalized at the batch level when forming advantages. This is the suggested approach from the paper
          [GDPO: Group reward-Decoupled Normalization Policy Optimization for Multi-reward RL
          Optimization](https://huggingface.co/papers/2601.05242).
    scale_rewards (`str` or `bool`, *optional*, defaults to `"group"`):
        Specifies the scaling strategy for rewards. Supported values are:

        - `True` or `"group"` (default): rewards are scaled by the standard deviation within each group, ensuring
          unit variance within a group.
        - `"batch"`: rewards are scaled by the standard deviation across the entire batch, as recommended in the
          [PPO Lite paper](https://huggingface.co/papers/2508.08221).
        - `False` or `"none"`: no scaling is applied. The [Dr. GRPO
          paper](https://huggingface.co/papers/2503.20783) recommends not scaling rewards, as scaling by the
          standard deviation introduces a question-level difficulty bias.
    loss_type (`str`, *optional*, defaults to `"dapo"`):
        Specifies the loss formulation to use. Supported values are:

        - `"grpo"`: Aggregates token-level losses by normalizing over sequence length. Not recommended due to
          length bias—this approach tends to prefer shorter completions with positive advantages and longer ones
          with negative advantages.
        - `"dr_grpo"`: Aggregates token-level losses by normalizing with a global constant. This method was
          introduced in the [Dr. GRPO paper](https://huggingface.co/papers/2503.20783) to eliminate length bias.
          The value of the constant corresponds to `max_completion_length`.
        - `"dapo"` (default): Aggregates token-level losses by normalizing with the number of active token in the
          global accumulated batch. This method was introduced in the [DAPO
          paper](https://huggingface.co/papers/2503.14476) to eliminate length bias.
        - `"bnpo"`: Aggregates token-level losses by normalizing with the number of active token in the local
          batch. Note that normalization is performed over the local batch only, so results may slightly vary
          depending on the local batch size, despite a constant effective batch size. When using
          `per_device_train_batch_size==1`, the loss is equivalent to the GRPO loss.
        - `"cispo"`: Clips the importance sampling weights instead of the advantage scaled importance weights. The
          clipped weights are then multiplied with the advantages and policy model's log probs. Individual token
          losses are aggregated by normalizing with the number of active tokens in the global accumulated batch.
          This method was introduced in the [MiniMax-M1 paper](https://huggingface.co/papers/2506.13585).
        - `"sapo"`: Soft Adaptive Policy Optimization loss, as introduced in the [Soft Adaptive Policy Optimization
          paper](https://huggingface.co/papers/2506.13585). Replaces hard clipping with a smooth,
          temperature-controlled gate that adaptively attenuates off-policy updates while preserving useful
          learning signals.
    mask_truncated_completions (`bool`, *optional*, defaults to `False`):
        When enabled, truncated completions are excluded from the loss calculation, preventing them from being
        incorrectly penalized and introducing noise during training. According to the
        [DAPO](https://huggingface.co/papers/2503.14476) paper, this is a good practice for training stability.
    sync_ref_model (`bool`, *optional*, defaults to `False`):
        Whether to synchronize the reference model with the active model every `ref_model_sync_steps` steps, using
        the `ref_model_mixup_alpha` parameter. This synchronization originates from the
        [TR-DPO](https://huggingface.co/papers/2404.09656) paper.
    ref_model_mixup_alpha (`float`, *optional*, defaults to `0.6`):
        α parameter from the [TR-DPO](https://huggingface.co/papers/2404.09656) paper, which controls the mix
        between the current policy and the previous reference policy during updates. The reference policy is
        updated according to the equation: `π_ref = α * π_θ + (1 - α) * π_ref_prev`. To use this parameter, you
        must set `sync_ref_model=True`.
    ref_model_sync_steps (`int`, *optional*, defaults to `512`):
        τ parameter from the [TR-DPO](https://huggingface.co/papers/2404.09656) paper, which determines how
        frequently the current policy is synchronized with the reference policy. To use this parameter, you must
        set `sync_ref_model=True`.
    top_entropy_quantile (`float`, *optional*, defaults to `1.0`):
        ρ parameter from [Beyond the 80/20 Rule](https://huggingface.co/papers/2506.01939). Keeps in the policy
        loss term only the top-ρ quantile of tokens by entropy of the probability distribution at each sequence
        position, improving results. Range: `[0.0-1.0]`. A value of `0.0` masks all but the highest entropy token;
        `1.0` keeps all tokens. The paper recommends a value of `0.2`. If used with
        `mask_truncated_completions=True`, only tokens from non-truncated completions are considered.
    max_tool_calling_iterations (`int`, *optional*):
        Maximum number of tool-calling turns when training an agent. If `None`, there is no limit and generation
        stops when the model generates a response turn with no tool calls or when the total response length reaches
        `max_model_length`.
    use_liger_loss (`bool`, *optional*):
        Whether to use Liger loss.

        <Deprecated version="0.25.0">

        Parameter `use_liger_loss` is deprecated and will be removed in version 0.28.0. Use `use_liger_kernel`
        instead.

        </Deprecated>
    vllm_importance_sampling_correction (`bool`, *optional*, defaults to `True`):
        Whether to apply Importance Sampling (IS) to correct for the mismatch between vLLM completion logprobs and
        recomputed training logprobs. If set to `False`, no IS is applied regardless of
        `vllm_importance_sampling_mode`. When `True`, the selected mode determines how the IS ratios are computed
        and constrained.
    vllm_importance_sampling_mode (`str`, *optional*, defaults to `"sequence_mask"`):
        Specifies how Importance Sampling is performed when `vllm_importance_sampling_correction=True`. Possible
        values are:

            - `"token_truncate"`: Token-level truncated IS (default). Per-token ratios are clipped from above at C.
            - `"token_mask"`: Token-level masked IS. Per-token ratios above C are set to zero.
            - `"sequence_truncate"`: Sequence-level truncated IS. A single sequence ratio is clipped from above at
              C and applied to all tokens in the sequence.
            - `"sequence_mask"`: Sequence-level masked IS. Sequences with ratios above C are masked out.
    vllm_importance_sampling_cap (`float`, *optional*, defaults to `3.0`):
        Importance sampling cap C used by `vllm_importance_sampling_mode`. For `*_truncate` modes, importance
        ratios are clipped from above at C. For `*_mask` modes, ratios larger than C are set to zero.
    off_policy_mask_threshold (`float`, *optional*):
        Threshold for off-policy sequence masking. If `None`, off-policy sequence masking is disabled. When set,
        sequences with negative advantages and high KL divergence are masked out to stabilize training. This
        parameter corresponds to the `delta` threshold in Equation 9 of the [DeepSeek-V3.2
        paper](https://huggingface.co/papers/2512.02556). It expects a positive value (e.g., 0.5).
    use_bias_correction_kl (`bool`, *optional*, defaults to `False`):
        Whether to use the unbiased KL divergence estimator with importance sampling correction. This corrects the
        KL divergence estimate by multiplying it with the importance sampling ratio. This is described in the
        [DeepSeek-V3.2 paper](https://huggingface.co/papers/2512.02556).

    > Parameters that control the logging

    log_completions (`bool`, *optional*, defaults to `False`):
        Whether to log a sample of (prompt, completion) pairs every `logging_steps` steps. If `rich` is installed,
        it prints the sample. If `wandb` and/or `trackio` logging is enabled, it logs it to `wandb` and/or
        `trackio`.
    num_completions_to_print (`int`, *optional*):
        Number of completions to print with `rich`. If `None`, all completions are logged.
    log_unique_prompts (`bool`, *optional*, defaults to `False`):
        Whether to log unique prompts. If `True`, only unique prompts are logged. If `False`, all prompts are
        logged.

    > Deprecated arguments

    max_prompt_length:

        <Deprecated version="0.26.0">

        Parameter `max_prompt_length` is deprecated and will be removed in version 0.28.0. You should instead
        filter your dataset before training to ensure that prompts do not exceed your desired length.

        </Deprecated>

    vllm_guided_decoding_regex:

        <Deprecated version="0.27.0">

        Parameter `vllm_guided_decoding_regex` is deprecated and will be removed in version 0.28.0. You should
        instead use `vllm_structured_outputs_regex`.

        </Deprecated>

    """
    vllm_sampling_params: Optional[Any] = field(
        default = None,
        metadata = {'help': 'vLLM SamplingParams'},
    )
    unsloth_num_chunks : Optional[int] = field(
        default = -1,
        metadata = {'help': 'Chunk size to reduce memory usage. -1 is most efficient.'},
    )
    unsloth_logit_chunk_multiplier : Optional[int] = field(
            default = None,
            metadata = {'help': 'Multiplier for chunked logit computations.'},
        )
    unsloth_grpo_mini_batch : Optional[int] = field(
        default = None,
        metadata = {'help': 'Mini batch size for GRPO hidden state accumulation. Default is None unless user defines it.'},
    )
    
    def __init__(
        self,
        output_dir = None,
        do_train = False,
        do_eval = False,
        do_predict = False,
        eval_strategy = 'no',
        prediction_loss_only = False,
        per_device_train_batch_size = 4,
        per_device_eval_batch_size = 4,
        gradient_accumulation_steps = 2,
        eval_accumulation_steps = 2,
        eval_delay = 0,
        torch_empty_cache_steps = 250,
        learning_rate = 5e-05,
        weight_decay = 0.01,
        adam_beta1 = 0.9,
        adam_beta2 = 0.999,
        adam_epsilon = 1e-08,
        max_grad_norm = 1.0,
        num_train_epochs = 3.0,
        max_steps = -1,
        lr_scheduler_type = 'linear',
        lr_scheduler_kwargs = None,
        warmup_ratio = 0.1,
        warmup_steps = 0,
        log_level = 'passive',
        log_level_replica = 'warning',
        log_on_each_node = True,
        logging_dir = None,
        logging_strategy = 'steps',
        logging_first_step = False,
        logging_steps = 1,
        logging_nan_inf_filter = False,
        save_strategy = 'steps',
        save_steps = 500,
        save_total_limit = None,
        enable_jit_checkpoint = False,
        save_on_each_node = False,
        save_only_model = False,
        restore_callback_states_from_checkpoint = False,
        use_cpu = False,
        seed = 3407,
        data_seed = 3407,
        bf16 = False,
        fp16 = False,
        bf16_full_eval = False,
        fp16_full_eval = False,
        tf32 = None,
        local_rank = -1,
        ddp_backend = None,
        debug = '',
        dataloader_drop_last = False,
        eval_steps = None,
        dataloader_num_workers = 0,
        dataloader_prefetch_factor = None,
        run_name = None,
        disable_tqdm = None,
        remove_unused_columns = False,
        label_names = None,
        load_best_model_at_end = False,
        metric_for_best_model = None,
        greater_is_better = None,
        ignore_data_skip = False,
        fsdp = None,
        fsdp_config = None,
        accelerator_config = None,
        parallelism_config = None,
        deepspeed = None,
        label_smoothing_factor = 0.0,
        optim = 'adamw_8bit',
        optim_args = None,
        group_by_length = False,
        length_column_name = 'length',
        report_to = 'none',
        project = 'huggingface',
        trackio_space_id = 'trackio',
        ddp_find_unused_parameters = None,
        ddp_bucket_cap_mb = None,
        ddp_broadcast_buffers = None,
        dataloader_pin_memory = True,
        dataloader_persistent_workers = False,
        skip_memory_metrics = True,
        push_to_hub = False,
        resume_from_checkpoint = None,
        hub_model_id = None,
        hub_strategy = 'every_save',
        hub_token = None,
        hub_private_repo = None,
        hub_always_push = False,
        hub_revision = None,
        gradient_checkpointing = True,
        gradient_checkpointing_kwargs = None,
        eval_do_concat_batches = True,
        auto_find_batch_size = False,
        full_determinism = False,
        ddp_timeout = 1800,
        torch_compile = False,
        torch_compile_backend = None,
        torch_compile_mode = None,
        include_num_input_tokens_seen = False,
        neftune_noise_alpha = None,
        optim_target_modules = None,
        batch_eval_metrics = False,
        eval_on_start = False,
        use_liger_kernel = False,
        liger_kernel_config = None,
        eval_use_gather_object = False,
        average_tokens_across_devices = True,
        use_cache = False,
        model_init_kwargs = None,
        disable_dropout = False,
        cast_lm_head_to_fp32 = False,
        num_generations = 8,
        num_generations_eval = None,
        max_completion_length = 256,
        ds3_gather_for_generation = True,
        shuffle_dataset = True,
        generation_batch_size = None,
        steps_per_generation = None,
        temperature = 1.0,
        top_p = 1.0,
        top_k = None,
        min_p = None,
        generation_kwargs = {},
        chat_template_kwargs = None,
        repetition_penalty = 1.0,
        use_transformers_paged = False,
        cache_implementation = None,
        use_vllm = False,
        vllm_mode = 'colocate',
        vllm_model_impl = 'vllm',
        vllm_enable_sleep_mode = False,
        vllm_structured_outputs_regex = None,
        vllm_server_base_url = None,
        vllm_server_host = '0.0.0.0',
        vllm_server_port = 8000,
        vllm_server_timeout = 240.0,
        vllm_group_port = 51216,
        vllm_gpu_memory_utilization = 0.3,
        vllm_max_model_length = None,
        vllm_tensor_parallel_size = 1,
        beta = 0.001,
        num_iterations = 1,
        epsilon = 0.2,
        delta = None,
        epsilon_high = None,
        sapo_temperature_neg = 1.05,
        sapo_temperature_pos = 1.0,
        importance_sampling_level = 'token',
        reward_weights = None,
        multi_objective_aggregation = 'sum_then_normalize',
        scale_rewards = 'group',
        loss_type = 'bnpo',
        mask_truncated_completions = False,
        sync_ref_model = False,
        ref_model_mixup_alpha = 0.6,
        ref_model_sync_steps = 512,
        top_entropy_quantile = 1.0,
        max_tool_calling_iterations = None,
        use_liger_loss = None,
        vllm_importance_sampling_correction = False,
        vllm_importance_sampling_mode = 'sequence_mask',
        vllm_importance_sampling_cap = 3.0,
        off_policy_mask_threshold = None,
        use_bias_correction_kl = False,
        log_completions = False,
        num_completions_to_print = None,
        log_unique_prompts = False,
        max_prompt_length = None,
        vllm_guided_decoding_regex = None,
        vllm_sampling_params = None,
        unsloth_num_chunks = -1,
        unsloth_logit_chunk_multiplier = None, 
        unsloth_grpo_mini_batch = None, 
        
        **kwargs,
    ):
        if learning_rate < 1e-7: print(f'Unsloth: Your learning rate of `{learning_rate}` is too small and less than 1e-7! Consider increasing it, otherwise gradient updates will be close to 0!')
        if learning_rate > 1: print(f'Unsloth: Your learning rate of `{learning_rate}` is way too larger > 1! Consider decreasing it to 1e-1, otherwise gradient updates will explode!')
        if output_dir is None and save_strategy == 'steps' and save_steps == 500:
            output_dir = 'unsloth_training_checkpoints'
            save_strategy = 'no'
        if loss_type.lower() == 'dr_grpo':
            loss_type = 'dr_grpo'
        elif loss_type.lower() == 'dapo':
            loss_type = 'dapo'
        if loss_type.lower() == 'dr_grpo':
            if scale_rewards == None:
                scale_rewards = True
            elif scale_rewards == True:
                print('Unsloth: The Dr GRPO paper recommends setting `scale_rewards` to False! Will override. Set it to `None` to force False.')
                scale_rewards = False
        elif loss_type.lower() == 'dapo':
            if mask_truncated_completions != True:
                print('Unsloth: The DAPO paper recommends `mask_truncated_completions = True` - we will set it.')
            if epsilon_high != 0.28:
                print('Unsloth: The DAPO paper recommends `epsilon_high = 0.28` - we will set it.')
            if beta != 0.0:
                print(f'[WARNING] Unsloth: The DAPO paper recommends setting `beta = 0.0` to remove the KL term - You have set it to {beta}.')
            mask_truncated_completions = True
            epsilon_high = 0.28
        
        if steps_per_generation is None and generation_batch_size is None:
            ga = gradient_accumulation_steps
            world_size = int(os.environ.get('WORLD_SIZE', '1'))
            if (ga * world_size * per_device_train_batch_size) % num_generations != 0:
                print('Unsloth: We now expect `per_device_train_batch_size` * `gradient_accumulation_steps` * `world_size` to be a multiple of `num_generations`.\nWe will change the batch size of ' + str(per_device_train_batch_size) + ' to the `num_generations` of ' + str(num_generations))
                per_device_train_batch_size = num_generations
        
        if temperature <= 0:
            raise ValueError('Unsloth: Please set a positive non-zero temperature since your results will be wrong.')
        elif temperature >= 10:
            raise ValueError('Unsloth: Please set a positive non-zero temperature less than 10, since sampling will be quite erratic.')
        
        
        super().__init__(
            output_dir = output_dir,
            do_train = do_train,
            do_eval = do_eval,
            do_predict = do_predict,
            eval_strategy = eval_strategy,
            prediction_loss_only = prediction_loss_only,
            per_device_train_batch_size = per_device_train_batch_size,
            per_device_eval_batch_size = per_device_eval_batch_size,
            gradient_accumulation_steps = gradient_accumulation_steps,
            eval_accumulation_steps = eval_accumulation_steps,
            eval_delay = eval_delay,
            torch_empty_cache_steps = torch_empty_cache_steps,
            learning_rate = learning_rate,
            weight_decay = weight_decay,
            adam_beta1 = adam_beta1,
            adam_beta2 = adam_beta2,
            adam_epsilon = adam_epsilon,
            max_grad_norm = max_grad_norm,
            num_train_epochs = num_train_epochs,
            max_steps = max_steps,
            lr_scheduler_type = lr_scheduler_type,
            lr_scheduler_kwargs = lr_scheduler_kwargs,
            warmup_ratio = warmup_ratio,
            warmup_steps = warmup_steps,
            log_level = log_level,
            log_level_replica = log_level_replica,
            log_on_each_node = log_on_each_node,
            logging_dir = logging_dir,
            logging_strategy = logging_strategy,
            logging_first_step = logging_first_step,
            logging_steps = logging_steps,
            logging_nan_inf_filter = logging_nan_inf_filter,
            save_strategy = save_strategy,
            save_steps = save_steps,
            save_total_limit = save_total_limit,
            enable_jit_checkpoint = enable_jit_checkpoint,
            save_on_each_node = save_on_each_node,
            save_only_model = save_only_model,
            restore_callback_states_from_checkpoint = restore_callback_states_from_checkpoint,
            use_cpu = use_cpu,
            seed = seed,
            data_seed = data_seed,
            bf16 = bf16,
            fp16 = fp16,
            bf16_full_eval = bf16_full_eval,
            fp16_full_eval = fp16_full_eval,
            tf32 = tf32,
            local_rank = local_rank,
            ddp_backend = ddp_backend,
            debug = debug,
            dataloader_drop_last = dataloader_drop_last,
            eval_steps = eval_steps,
            dataloader_num_workers = dataloader_num_workers,
            dataloader_prefetch_factor = dataloader_prefetch_factor,
            run_name = run_name,
            disable_tqdm = disable_tqdm,
            remove_unused_columns = remove_unused_columns,
            label_names = label_names,
            load_best_model_at_end = load_best_model_at_end,
            metric_for_best_model = metric_for_best_model,
            greater_is_better = greater_is_better,
            ignore_data_skip = ignore_data_skip,
            fsdp = fsdp,
            fsdp_config = fsdp_config,
            accelerator_config = accelerator_config,
            parallelism_config = parallelism_config,
            deepspeed = deepspeed,
            label_smoothing_factor = label_smoothing_factor,
            optim = optim,
            optim_args = optim_args,
            group_by_length = group_by_length,
            length_column_name = length_column_name,
            report_to = report_to,
            project = project,
            trackio_space_id = trackio_space_id,
            ddp_find_unused_parameters = ddp_find_unused_parameters,
            ddp_bucket_cap_mb = ddp_bucket_cap_mb,
            ddp_broadcast_buffers = ddp_broadcast_buffers,
            dataloader_pin_memory = dataloader_pin_memory,
            dataloader_persistent_workers = dataloader_persistent_workers,
            skip_memory_metrics = skip_memory_metrics,
            push_to_hub = push_to_hub,
            resume_from_checkpoint = resume_from_checkpoint,
            hub_model_id = hub_model_id,
            hub_strategy = hub_strategy,
            hub_token = hub_token,
            hub_private_repo = hub_private_repo,
            hub_always_push = hub_always_push,
            hub_revision = hub_revision,
            gradient_checkpointing = gradient_checkpointing,
            gradient_checkpointing_kwargs = gradient_checkpointing_kwargs,
            eval_do_concat_batches = eval_do_concat_batches,
            auto_find_batch_size = auto_find_batch_size,
            full_determinism = full_determinism,
            ddp_timeout = ddp_timeout,
            torch_compile = torch_compile,
            torch_compile_backend = torch_compile_backend,
            torch_compile_mode = torch_compile_mode,
            include_num_input_tokens_seen = include_num_input_tokens_seen,
            neftune_noise_alpha = neftune_noise_alpha,
            optim_target_modules = optim_target_modules,
            batch_eval_metrics = batch_eval_metrics,
            eval_on_start = eval_on_start,
            use_liger_kernel = use_liger_kernel,
            liger_kernel_config = liger_kernel_config,
            eval_use_gather_object = eval_use_gather_object,
            average_tokens_across_devices = average_tokens_across_devices,
            use_cache = use_cache,
            model_init_kwargs = model_init_kwargs,
            disable_dropout = disable_dropout,
            cast_lm_head_to_fp32 = cast_lm_head_to_fp32,
            num_generations = num_generations,
            num_generations_eval = num_generations_eval,
            max_completion_length = max_completion_length,
            ds3_gather_for_generation = ds3_gather_for_generation,
            shuffle_dataset = shuffle_dataset,
            generation_batch_size = generation_batch_size,
            steps_per_generation = steps_per_generation,
            temperature = temperature,
            top_p = top_p,
            top_k = top_k,
            min_p = min_p,
            generation_kwargs = generation_kwargs,
            chat_template_kwargs = chat_template_kwargs,
            repetition_penalty = repetition_penalty,
            use_transformers_paged = use_transformers_paged,
            cache_implementation = cache_implementation,
            use_vllm = use_vllm,
            vllm_mode = vllm_mode,
            vllm_model_impl = vllm_model_impl,
            vllm_enable_sleep_mode = vllm_enable_sleep_mode,
            vllm_structured_outputs_regex = vllm_structured_outputs_regex,
            vllm_server_base_url = vllm_server_base_url,
            vllm_server_host = vllm_server_host,
            vllm_server_port = vllm_server_port,
            vllm_server_timeout = vllm_server_timeout,
            vllm_group_port = vllm_group_port,
            vllm_gpu_memory_utilization = vllm_gpu_memory_utilization,
            vllm_max_model_length = vllm_max_model_length,
            vllm_tensor_parallel_size = vllm_tensor_parallel_size,
            beta = beta,
            num_iterations = num_iterations,
            epsilon = epsilon,
            delta = delta,
            epsilon_high = epsilon_high,
            sapo_temperature_neg = sapo_temperature_neg,
            sapo_temperature_pos = sapo_temperature_pos,
            importance_sampling_level = importance_sampling_level,
            reward_weights = reward_weights,
            multi_objective_aggregation = multi_objective_aggregation,
            scale_rewards = scale_rewards,
            loss_type = loss_type,
            mask_truncated_completions = mask_truncated_completions,
            sync_ref_model = sync_ref_model,
            ref_model_mixup_alpha = ref_model_mixup_alpha,
            ref_model_sync_steps = ref_model_sync_steps,
            top_entropy_quantile = top_entropy_quantile,
            max_tool_calling_iterations = max_tool_calling_iterations,
            use_liger_loss = use_liger_loss,
            vllm_importance_sampling_correction = vllm_importance_sampling_correction,
            vllm_importance_sampling_mode = vllm_importance_sampling_mode,
            vllm_importance_sampling_cap = vllm_importance_sampling_cap,
            off_policy_mask_threshold = off_policy_mask_threshold,
            use_bias_correction_kl = use_bias_correction_kl,
            log_completions = log_completions,
            num_completions_to_print = num_completions_to_print,
            log_unique_prompts = log_unique_prompts,
            max_prompt_length = max_prompt_length,
            vllm_guided_decoding_regex = vllm_guided_decoding_regex,**kwargs)
        self.vllm_sampling_params = vllm_sampling_params
        self.unsloth_num_chunks = unsloth_num_chunks
        if unsloth_grpo_mini_batch is not None:
            if self.generation_batch_size >= unsloth_grpo_mini_batch:
                self.unsloth_grpo_mini_batch = unsloth_grpo_mini_batch
            else:
                raise ValueError(
                    f"Unsloth GRPO mini batch size needs to be less than or equal to the effective generation batch size, "
                    f"which is self.per_device_train_batch_size * gradient_accumulation_steps."
                )
        self.unsloth_logit_chunk_multiplier = unsloth_logit_chunk_multiplier
        
pass

class _UnslothGRPOTrainer(BaseTrainer):
    """
    Trainer for the Group Relative Policy Optimization (GRPO) method. This algorithm was initially proposed in the
    paper [DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language
    Models](https://huggingface.co/papers/2402.03300).

    Example:

    ```python
    from trl import GRPOTrainer
    from trl.rewards import accuracy_reward
    from datasets import load_dataset

    dataset = load_dataset("trl-lib/DeepMath-103K", split="train")

    trainer = GRPOTrainer(
        model="Qwen/Qwen2.5-0.5B-Instruct",
        reward_funcs=accuracy_reward,
        train_dataset=dataset,
    )
    trainer.train()
    ```

    Args:
        model (`str` or [`~transformers.PreTrainedModel`] or [`~peft.PeftModel`]):
            Model to be trained. Can be either:

            - A string, being the *model id* of a pretrained model hosted inside a model repo on huggingface.co, or a
              path to a *directory* containing model weights saved using
              [`~transformers.PreTrainedModel.save_pretrained`], e.g., `'./my_model_directory/'`. The model is loaded
              using `<ModelArchitecture>.from_pretrained` (where `<ModelArchitecture>` is derived from the model
              config) with the keyword arguments in `args.model_init_kwargs`.
            - A [`~transformers.PreTrainedModel`] object. Only causal language models are supported.
            - A [`~peft.PeftModel`] object. Only causal language models are supported.
        reward_funcs (`RewardFunc | list[RewardFunc]`):
            Reward functions to be used for computing the rewards. To compute the rewards, we call all the reward
            functions with the prompts and completions and sum the rewards. Can be either:

            - A single reward function, such as:
                - A string: The *model ID* of a pretrained model hosted inside a model repo on huggingface.co, or a
                path to a *directory* containing model weights saved using
                [`~transformers.PreTrainedModel.save_pretrained`], e.g., `'./my_model_directory/'`. The model is loaded
                using [`~transformers.AutoModelForSequenceClassification.from_pretrained`] with `num_labels=1` and the
                keyword arguments in `args.model_init_kwargs`.
                - A [`~transformers.PreTrainedModel`] object: Only sequence classification models are supported.
                - A custom reward function: The function is provided with the prompts and the generated completions,
                  plus any additional columns in the dataset. It should return a list of rewards. Custom reward
                   functions can be either synchronous or asynchronous and can also return `None` when the reward is
                   not applicable to those samples. This is useful for multi-task training where different reward
                   functions apply to different types of samples. When a reward function returns `None` for a sample,
                   that reward function is excluded from the reward calculation for that sample. For more details, see
                   [Using a custom reward
                  function](#using-a-custom-reward-function).

                  The trainer's state is also passed to the reward function. The trainer's state is an instance of
                  [`~transformers.TrainerState`] and can be accessed by accessing the `trainer_state` argument to the
                  reward function's signature.
            - A list of reward functions, where each item can independently be any of the above types. Mixing different
            types within the list (e.g., a string model ID and a custom reward function) is allowed.
        args ([`GRPOConfig`], *optional*):
            Configuration for this trainer. If `None`, a default configuration is used.
        train_dataset ([`~datasets.Dataset`] or [`~datasets.IterableDataset`]):
            Dataset to use for training. It must include a column `"prompt"`. Any additional columns in the dataset is
            ignored. The format of the samples can be either:

            - [Standard](dataset_formats#standard): Each sample contains plain text.
            - [Conversational](dataset_formats#conversational): Each sample contains structured messages (e.g., role
              and content).
        eval_dataset ([`~datasets.Dataset`], [`~datasets.IterableDataset`] or `dict[str, Dataset | IterableDataset]`):
            Dataset to use for evaluation. It must meet the same requirements as `train_dataset`.
        processing_class ([`~transformers.PreTrainedTokenizerBase`], [`~transformers.ProcessorMixin`], *optional*):
            Processing class used to process the data. The padding side must be set to "left". If `None`, the
            processing class is loaded from the model's name with [`~transformers.AutoProcessor.from_pretrained`]. A
            padding token, `tokenizer.pad_token`, must be set. If the processing class has not set a padding token,
            `tokenizer.eos_token` will be used as the default.
        reward_processing_classes ([`~transformers.PreTrainedTokenizerBase`] or `list[PreTrainedTokenizerBase]`, *optional*):
            Processing classes corresponding to the reward functions specified in `reward_funcs`. Can be either:

            - A single processing class: Used when `reward_funcs` contains only one reward function.
            - A list of processing classes: Must match the order and length of the reward functions in `reward_funcs`.
            If set to `None`, or if an element of the list corresponding to a [`~transformers.PreTrainedModel`] is
            `None`, the tokenizer for the model is automatically loaded using
            [`~transformers.AutoTokenizer.from_pretrained`]. For elements in `reward_funcs` that are custom reward
            functions (not [`~transformers.PreTrainedModel`]), the corresponding entries in `reward_processing_classes`
            are ignored.
        callbacks (list of [`~transformers.TrainerCallback`], *optional*):
            List of callbacks to customize the training loop. Will add those to the list of default callbacks detailed
            in [here](https://huggingface.co/docs/transformers/main_classes/callback).

            If you want to remove one of the default callbacks used, use the [`~transformers.Trainer.remove_callback`]
            method.
        optimizers (`tuple[torch.optim.Optimizer | None, torch.optim.lr_scheduler.LambdaLR | None]`, *optional*, defaults to `(None, None)`):
            A tuple containing the optimizer and the scheduler to use. Will default to an instance of `AdamW` on your
            model and a scheduler given by [`~transformers.get_linear_schedule_with_warmup`] controlled by `args`.
        peft_config ([`~peft.PeftConfig`], *optional*):
            PEFT configuration used to wrap the model. If `None`, the model is not wrapped.
        tools (list of `Callable`, *optional*):
            A list of callable tool functions that the model can invoke during generation. Each tool should be a
            standard Python function with properly type-hinted arguments and return values, and a Google-style
            docstring describing its purpose, arguments, and return value. For more details, see:
            https://huggingface.co/docs/transformers/en/chat_extras#passing-tools. The model uses the function's name,
            type hints, and docstring to determine how to call it. Ensure that the model's chat template supports tool
            use and that it has been fine-tuned for tool calling.
        rollout_func (`RolloutFunc`, *optional*):
            Function to use for generating completions. It receives the list of prompts allocated to the current
            process and the trainer instance. It must return a dict with `"prompt_ids"`, `"completion_ids"`, and
            `"logprobs"` fields. Any other fields are forwarded to the reward functions. This feature is experimental
            and may change or be removed at any time without prior notice.
    """

    _tag_names = ["trl", "grpo"]
    _name = "GRPO"
    _paper = {
        "title": "DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models",
        "id": "2402.03300",
        # docstyle-ignore
        "citation": textwrap.dedent("""\
            @article{shao2024deepseekmath,
                title        = {{DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models}},
                author       = {Zhihong Shao and Peiyi Wang and Qihao Zhu and Runxin Xu and Junxiao Song and Mingchuan Zhang and Y. K. Li and Y. Wu and Daya Guo},
                year         = 2024,
                eprint       = {arXiv:2402.03300},
            }
            """),
    }

    def __init__(
        self,
        model: "str | PreTrainedModel | PeftModel",
        reward_funcs: RewardFunc | list[RewardFunc],
        args: GRPOConfig | None = None,
        train_dataset: Dataset | IterableDataset | None = None,
        eval_dataset: Dataset | IterableDataset | dict[str, Dataset | IterableDataset] | None = None,
        processing_class: PreTrainedTokenizerBase | ProcessorMixin | None = None,
        reward_processing_classes: PreTrainedTokenizerBase | list[PreTrainedTokenizerBase] | None = None,
        callbacks: list[TrainerCallback] | None = None,
        optimizers: tuple[torch.optim.Optimizer | None, torch.optim.lr_scheduler.LambdaLR | None] = (None, None),
        peft_config: "PeftConfig | None" = None,
        tools: list[Callable] | None = None,
        rollout_func: RolloutFunc | None = None,
    ):

        if hasattr(model, 'vllm_engine') and hasattr(args, 'use_vllm'):
            if (getattr(args, 'use_vllm', False) == False):
                args.use_vllm = True
            args.vllm_mode='colocate'
            if os.environ.get('UNSLOTH_VLLM_STANDBY', '0') == '1':
                args.vllm_enable_sleep_mode=True
        # Args
        if args is None:
            model_name = model if isinstance(model, str) else get_config_model_id(model.config)
            model_name = model_name.split("/")[-1]
            args = GRPOConfig(f"{model_name}-GRPO")

        # Model
        if isinstance(model, str):
            model_init_kwargs = args.model_init_kwargs or {}
            # Distributed training requires device_map=None ["auto" fails]
            if args.distributed_state.distributed_type in ["MULTI_GPU", "DEEPSPEED"]:
                model_init_kwargs["device_map"] = None
            model = create_model_from_path(model, **model_init_kwargs)
        else:
            if args.model_init_kwargs is not None:
                logger.warning(
                    "You passed `model_init_kwargs` to the `GRPOConfig`, but your model is already instantiated. "
                    "The `model_init_kwargs` will be ignored."
                )

        # Some models [SmolVLM/Idefics3] don't support `logits_to_keep` argument and error out if we pass it
        # Inspect the forward method before we wrap the model with PEFT
        self.model_kwarg_keys = (
            inspect.signature(model.forward).parameters.keys()
            if not hasattr(model, "get_base_model")
            else inspect.signature(model.get_base_model().forward).parameters.keys()
        )

        # Processing class
        if processing_class is None:
            processing_class = AutoProcessor.from_pretrained(
                get_config_model_id(model.config), truncation_side="left", padding_side="left"
            )

        # Handle pad token for processors or tokenizers
        if isinstance(processing_class, ProcessorMixin):
            tokenizer = processing_class.tokenizer
        elif isinstance(processing_class, PreTrainedTokenizerBase):
            tokenizer = processing_class
        else:
            raise TypeError("The `processing_class` must be either a `PreTrainedTokenizerBase` or a `ProcessorMixin`")

        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        self.pad_token = tokenizer.pad_token
        self.pad_token_id = tokenizer.pad_token_id
        self.eos_token_id = tokenizer.eos_token_id

        if is_peft_available() and is_peft_model(model) and peft_config is not None:
            raise ValueError(
                "You passed a `PeftModel` instance together with a `peft_config` to the trainer. Please first merge "
                "and unload the existing adapter, save the resulting base model, and then pass that base model along "
                "with the new `peft_config` to the trainer."
            )

        # Unsloth: Commented out - use base model as reference, not SFT/LoRA model
        # if is_peft_available() and is_peft_model(model) and args.beta != 0.0:
            # # If the model is a PEFT model with a pretrained adapter, we need to create a "ref" adapter that is a copy
            # # of the "default" adapter, so that we can use it as the reference model during GRPO training.
            # model.add_adapter("ref", model.peft_config["default"])
            # for name, param in model.named_parameters():
                # if ".default." in name:
                    # ref_name = name.replace(".default.", ".ref.")
                    # ref_param = model.get_parameter(ref_name)
                    # ref_param.data.copy_(param.data)

        # Create PEFT model
        if False:
            model = model

        # When using gradient checkpointing with PEFT, we need to enable input gradients. transformers.Trainer normally
        # handles this, but a bug currently prevents it; see https://github.com/huggingface/transformers/issues/42489
        if is_peft_available() and is_peft_model(model) and args.gradient_checkpointing:
            model.enable_input_require_grads()

        # When using QLoRA, the PEFT adapter weights are converted to bf16 to follow the recommendations from the
        # original paper [see https://huggingface.co/papers/2305.14314, paragraph 3]. Normally, this can be done by
        # passing `autocast_adapter_dtype=False` to `get_peft_model`, but this option is not yet supported for
        # quantized models. See: https://github.com/huggingface/peft/issues/2889
        # Non-quantized models do not have the `is_loaded_in_{8,4}bit` attributes, whereas quantized models do
        if getattr(model, "is_loaded_in_4bit", False) or getattr(model, "is_loaded_in_8bit", False):
            for param in model.parameters():
                if param.requires_grad:
                    param.data = param.data.to(torch.bfloat16)

        # Reward functions
        if not isinstance(reward_funcs, list):
            reward_funcs = [reward_funcs]
        self.reward_func_names = []
        for i, reward_func in enumerate(reward_funcs):
            if isinstance(reward_func, str):
                model_init_kwargs = args.model_init_kwargs or {}
                # Special case for DeepSpeed: requires device_map=None ["auto" fails]
                if args.distributed_state.distributed_type == "DEEPSPEED":
                    model_init_kwargs["device_map"] = None
                reward_funcs[i] = AutoModelForSequenceClassification.from_pretrained(
                    reward_func, num_labels=1, **model_init_kwargs
                )
            if isinstance(reward_funcs[i], nn.Module):  # Use Module over PretrainedModel for compat w/ compiled models
                self.reward_func_names.append(get_config_model_id(reward_funcs[i].config).split("/")[-1])
            else:
                self.reward_func_names.append(reward_funcs[i].__name__)
        self.reward_funcs = reward_funcs

        self._has_async_reward_funcs = any(asyncio.iscoroutinefunction(func) for func in self.reward_funcs)
        if self._has_async_reward_funcs:
            self.async_reward_loop_thread, self.async_reward_loop, self.async_reward_loop_ready_event = (
                start_event_loop_in_daemon(name="GRPOTrainer-AsyncRewardLoop")
            )
            # wait until the event loop is running in the daemon thread
            self.async_reward_loop_ready_event.wait()
            atexit.register(shutdown_event_loop_in_daemon, self.async_reward_loop_thread, self.async_reward_loop)

        # Reward weights
        if args.reward_weights is not None:
            if len(args.reward_weights) != len(reward_funcs):
                raise ValueError(
                    f"Number of reward weights ({len(args.reward_weights)}) must match number of reward "
                    f"functions ({len(reward_funcs)})"
                )
            self.reward_weights = torch.tensor(args.reward_weights, dtype=torch.float32)
        else:
            self.reward_weights = torch.ones(len(reward_funcs), dtype=torch.float32)

        # Reward processing class
        if reward_processing_classes is None:
            reward_processing_classes = [None] * len(reward_funcs)
        elif not isinstance(reward_processing_classes, list):
            reward_processing_classes = [reward_processing_classes]
        if len(reward_processing_classes) != len(reward_funcs):
            raise ValueError(
                f"The number of reward processing classes ({len(reward_processing_classes)}) must match the number of "
                f"reward functions ({len(reward_funcs)})."
            )

        for i, (reward_processing_class, reward_func) in enumerate(
            zip(reward_processing_classes, reward_funcs, strict=True)
        ):
            if isinstance(reward_func, PreTrainedModel):
                if reward_processing_class is None:
                    reward_processing_class = AutoTokenizer.from_pretrained(get_config_model_id(reward_func.config))
                if reward_processing_class.pad_token_id is None:
                    reward_processing_class.pad_token = reward_processing_class.eos_token
                # The reward model computes the reward for the latest non-padded token in the input sequence.
                # So it's important to set the pad token ID to the padding token ID of the processing class.
                reward_func.config.pad_token_id = reward_processing_class.pad_token_id
                reward_processing_classes[i] = reward_processing_class

        self.reward_processing_classes = reward_processing_classes

        # Rollout function
        if rollout_func is not None and os.environ.get("TRL_EXPERIMENTAL_SILENCE", "0") != "1":
            warnings.warn(
                "You are importing from 'rollout_func', which is an experimental feature. This API may change or be "
                "removed at any time without prior notice. Silence this warning by setting environment variable "
                "TRL_EXPERIMENTAL_SILENCE=1.",
                UserWarning,
                stacklevel=2,
            )
        self.rollout_func = rollout_func

        # Tools
        if tools:
            if not Version(transformers.__version__) >= Version("5.0.0.dev0"):
                raise ImportError(
                    "Using tools with GRPOTrainer requires transformers version 5.0.0 or higher. Please use "
                    "transformers with `pip install --pre transformers` to use this feature."
                )
            if not is_jmespath_available():
                raise ImportError(
                    "Using tools with GRPOTrainer requires the jmespath library for response parsing. Please install "
                    "it with `pip install jmespath` to use this feature."
                )
        self.tools = tools
        if self.tools:
            self._tool_dict = {tool.__name__: tool for tool in self.tools}
        # At the time of initial implementation, most tokenizers do not have built-in support for response schemas.
        # While waiting for broader adoption, we provide this utility function to manually set the response schema for
        # known chat templates.
        # We need `getattr`` until the base class sets a default None value for response_schema
        if tools and not getattr(processing_class, "response_schema", None):
            processing_class = add_response_schema(processing_class)
        # In multi-turn training, the chat template *must* be prefix-preserving. If the tokenizer's original template
        # isn't, we replace it at initialization with a training-safe, prefix-preserving template.
        if tools:
            self.chat_template = get_training_chat_template(processing_class)
        else:
            self.chat_template = None

        # Training arguments
        self.max_completion_length = args.max_completion_length  # = |o_i| in the GRPO paper
        self.num_generations = args.num_generations  # = G in the GRPO paper
        self.max_tool_calling_iterations = args.max_tool_calling_iterations or sys.maxsize
        self.num_generations_eval = args.num_generations_eval or self.num_generations
        self.chat_template_kwargs = args.chat_template_kwargs or {}
        self.temperature = args.temperature
        self.top_p = args.top_p
        self.top_k = args.top_k
        self.min_p = args.min_p
        self.repetition_penalty = args.repetition_penalty
        self.use_transformers_paged = args.use_transformers_paged
        self.use_vllm = args.use_vllm
        self.vllm_mode = args.vllm_mode
        self.vllm_gpu_memory_utilization = args.vllm_gpu_memory_utilization  # only applies to colocation mode
        self.vllm_tensor_parallel_size = args.vllm_tensor_parallel_size  # only applies to colocation mode
        self.vllm_importance_sampling_correction = args.vllm_importance_sampling_correction
        self.vllm_importance_sampling_mode = args.vllm_importance_sampling_mode
        self.vllm_importance_sampling_cap = args.vllm_importance_sampling_cap
        self.use_liger_kernel = args.use_liger_kernel
        self.loss_type = args.loss_type
        self.multi_objective_aggregation = args.multi_objective_aggregation
        self.scale_rewards = args.scale_rewards
        self.importance_sampling_level = args.importance_sampling_level
        self.off_policy_mask_threshold = args.off_policy_mask_threshold
        if self.use_liger_kernel and self.off_policy_mask_threshold is not None:
            raise ValueError("Liger kernel does not support off-policy sequence masking yet.")
        self.mask_truncated_completions = args.mask_truncated_completions
        self.top_entropy_quantile = args.top_entropy_quantile
        if self.use_liger_kernel and self.top_entropy_quantile < 1.0:
            raise NotImplementedError(
                "Liger Kernels don't currently support masking token positions based on entropy."
            )
        if self.use_liger_kernel and not self.importance_sampling_level == "token":
            raise NotImplementedError(
                "Liger Kernels currently only support token-level importance sampling. Please set"
                "`importance_sampling_level` to 'token'."
            )

        # Datasets
        self.shuffle_dataset = args.shuffle_dataset

        if (
            isinstance(train_dataset, IterableDataset)
            or isinstance(eval_dataset, IterableDataset)
            or (
                isinstance(eval_dataset, dict) and any(isinstance(ds, IterableDataset) for ds in eval_dataset.values())
            )
        ):
            # See https://github.com/huggingface/trl/issues/3213
            raise NotImplementedError(
                "Iterable datasets are not yet supported in GRPOTrainer. Please use a standard dataset instead."
            )

        if args.loss_type == "sapo" and (args.sapo_temperature_neg is None or args.sapo_temperature_pos is None):
            raise ValueError(
                "When using `sapo` loss, both `sapo_temperature_neg` and `sapo_temperature_pos` must be set."
            )

        # Multi-step
        self.num_iterations = args.num_iterations  # = 𝜇 in the GRPO paper
        self.epsilon_low = args.epsilon
        self.epsilon_high = args.epsilon_high if args.epsilon_high is not None else args.epsilon
        # Tracks the number of iterations [forward + backward passes], including those within a grad accum cycle
        self._step = 0
        # Buffer the batch to reuse generated outputs across multiple updates. For more details, see
        # `_get_train_sampler` and `_prepare_inputs`.
        self._buffered_inputs = None

        super().__init__(
            model=model,
            args=args,
            data_collator=identity,  # No data collation is needed in GRPO
            train_dataset=train_dataset,
            eval_dataset=eval_dataset,
            processing_class=processing_class,
            callbacks=callbacks,
            optimizers=optimizers,
            # In Trainer, `training_step` scales the loss by `gradient_accumulation_steps` only if `compute_loss_func`
            # is None. For DAPO, loss scaling instead depends on the total number of completions tokens across the
            # global accumulated batch. To control scaling ourselves, we must disable Trainer’s built-in scaling. The
            # simplest [though a bit hacky] way is to set `compute_loss_func` to any non-None value, which bypasses
            # that behavior without rewriting `training_step`.
            compute_loss_func="non-None value to disable scaling",
        )

        # Reference model
        self.beta = args.beta
        if self.beta == 0.0:
            # If beta is 0.0, the reference model is not needed
            self.ref_model = None
        elif is_peft_model(model):
            # If PEFT is used, the reference model is not needed since the adapter can be disabled
            # to revert to the initial model.
            self.ref_model = None
        else:
            # For deepspeed, fsdp or non-distributed models, create a reference model from scratch
            model_init_kwargs = args.model_init_kwargs or {}
            # Special case for DeepSpeed: requires device_map=None ["auto" fails]
            if self.args.distributed_state.distributed_type == "DEEPSPEED":
                model_init_kwargs["device_map"] = None
            self.ref_model = create_model_from_path(get_config_model_id(self.model.config), **model_init_kwargs)

        # Disable dropout in the models
        if args.disable_dropout:
            disable_dropout_in_model(model)
            if self.ref_model is not None:
                disable_dropout_in_model(self.ref_model)

        # Cast LM Head To FP32
        if args.cast_lm_head_to_fp32:

            def _cast_lm_head_to_fp32(target_model: PreTrainedModel):
                """Cast lm_head to fp32 while preserving embedding output dtype if tied."""

                def cast_inputs_to_fp32(module, inputs):
                    # Preserve other positional args and kwargs untouched
                    if not inputs:
                        return inputs
                    return (inputs[0].to(torch.float32),) + inputs[1:]

                original_dtype_local = target_model.lm_head.weight.dtype
                target_model.lm_head = target_model.lm_head.float()
                target_model.lm_head.register_forward_pre_hook(cast_inputs_to_fp32)

                if target_model.config.tie_word_embeddings:

                    def cast_outputs_to_original_dtype(module, args, output):
                        return output.to(original_dtype_local)

                    # Only cast activations; weights are now fp32 [intentional for numerical stability of logits]
                    target_model.model.embed_tokens.register_forward_hook(cast_outputs_to_original_dtype)

            _cast_lm_head_to_fp32(model)
            if self.ref_model is not None:
                _cast_lm_head_to_fp32(self.ref_model)

        # Liger loss
        if self.use_liger_kernel:
            if not is_liger_kernel_available():
                raise ImportError(
                    "Liger is required to use `use_liger_kernel` as the GRPO loss. Run `pip install liger-kernel`."
                )
            # redirect the model.module forward to the model forward to ensure pre-forward hooks are called
            self._forward_redirection = _ForwardRedirection()

            self.liger_grpo_loss = LigerFusedLinearGRPOLoss(
                beta=self.beta,
                epsilon_low=self.epsilon_low,
                epsilon_high=self.epsilon_high,
                temperature=self.temperature,
                use_ref_model=self.beta != 0.0,
                loss_type=self.loss_type,
                max_completion_length=self.max_completion_length,
            )

        # Initialize the metrics
        self._metrics = {"train": defaultdict(list), "eval": defaultdict(list)}
        self._total_train_tokens = 0
        self._current_train_step_time = 0.0
        self.log_completions = args.log_completions
        self.log_unique_prompts = args.log_unique_prompts
        self.num_completions_to_print = args.num_completions_to_print
        # Keep logs sized to the generation batch to record only outputs from the latest model update.
        self._logs = {
            "images": deque(maxlen=args.generation_batch_size),
            "prompt": deque(maxlen=args.generation_batch_size),
            "completion": deque(maxlen=args.generation_batch_size),
            "rewards": defaultdict(lambda: deque(maxlen=args.generation_batch_size)),
            "advantages": deque(maxlen=args.generation_batch_size),
        }

        # Ensure each process receives a unique seed to prevent duplicate completions when generating with
        # transformers if num_generations exceeds per_device_train_batch_size. We could skip it if we use vLLM, but
        # it's safer to set it in all cases.
        set_seed(args.seed, device_specific=True)

        if self.use_vllm:
            if not is_vllm_available():
                raise ImportError(
                    "vLLM is not available and `use_vllm` is set to True. Please install vLLM with "
                    "`pip install trl[vllm]` to use it."
                )

            if self.vllm_mode == "server":
                if self.accelerator.is_main_process:
                    if args.vllm_server_base_url is not None:
                        base_url = args.vllm_server_base_url
                    else:
                        base_url = f"http://{args.vllm_server_host}:{args.vllm_server_port}"
                    self.vllm_client = VLLMClient(
                        base_url=base_url, group_port=args.vllm_group_port, connection_timeout=args.vllm_server_timeout
                    )
                    self.vllm_client.init_communicator(device=torch.cuda.current_device())

            elif self.vllm_mode == "colocate":
                if not self.accelerator.num_processes % self.vllm_tensor_parallel_size == 0:
                    raise ValueError(
                        f"vllm_tensor_parallel_size ({self.vllm_tensor_parallel_size}) must divide world size "
                        f"({self.accelerator.num_processes}) evenly."
                    )

                if self.vllm_tensor_parallel_size > 1:
                    self.tp_group, _ = torch.distributed.new_subgroups_by_enumeration(
                        [
                            list(range(i * self.vllm_tensor_parallel_size, (i + 1) * self.vllm_tensor_parallel_size))
                            for i in range(self.accelerator.num_processes // self.vllm_tensor_parallel_size)
                        ]
                    )
                os.environ["RANK"] = str(self.accelerator.process_index)
                os.environ["LOCAL_RANK"] = str(self.accelerator.local_process_index)
                os.environ["WORLD_SIZE"] = str(self.accelerator.num_processes)
                ensure_master_addr_port()

                vllm_quantization = None
                if is_bitsandbytes_available():
                    for _, module in model.named_modules():
                        if isinstance(module, bnb.nn.Linear4bit):
                            vllm_quantization = "bitsandbytes"
                            break
                        elif isinstance(module, bnb.nn.Linear8bitLt):
                            raise ValueError("vLLM does not support in-flight 8-bit quantization.")
                self.llm = model.vllm_engine
                if self.args.vllm_enable_sleep_mode:
                    self.llm.sleep(level=2)
            else:
                raise ValueError(f"vllm_mode must be either 'server' or 'colocate', got '{self.vllm_mode}'.")
            self.structured_outputs_regex = args.vllm_structured_outputs_regex

            self._last_loaded_step = -1
            self.accelerator.wait_for_everyone()
        else:
            generation_kwargs = {
                "max_new_tokens": self.max_completion_length,
                "do_sample": True,
                "pad_token_id": tokenizer.pad_token_id,
                "bos_token_id": tokenizer.bos_token_id,
                "eos_token_id": tokenizer.eos_token_id,
                "temperature": self.temperature,
                "top_p": self.top_p,
                "top_k": self.top_k,
                "min_p": self.min_p,
                "repetition_penalty": self.repetition_penalty,
                "cache_implementation": args.cache_implementation,
            }
            if args.generation_kwargs is not None:
                generation_kwargs.update(args.generation_kwargs)
            self.generation_config = GenerationConfig(**generation_kwargs)
            # Keep training-specific generation kwargs to overwrite model's original generation config
            self.generation_kwargs = generation_kwargs

        # Gradient accumulation requires scaled loss. Normally, loss scaling in the parent class depends on whether the
        # model accepts loss-related kwargs. Since we compute our own loss, this check is irrelevant. We set
        # self.model_accepts_loss_kwargs to False to enable scaling.
        self.model_accepts_loss_kwargs = False

        # Add tags to the model
        self.model.add_model_tags(self._tag_names)

        if self.ref_model is not None:
            if self.is_deepspeed_enabled:
                self.ref_model = prepare_deepspeed(self.ref_model, self.accelerator)
            elif self.is_fsdp_enabled:
                self.ref_model = prepare_fsdp(self.ref_model, self.accelerator)
            else:
                self.ref_model = self.accelerator.prepare_model(self.ref_model, evaluation_mode=True)

        if args.sync_ref_model:
            self.add_callback(SyncRefModelCallback(ref_model=self.ref_model, accelerator=self.accelerator))

        for i, reward_func in enumerate(self.reward_funcs):
            if isinstance(reward_func, PreTrainedModel):
                if self.is_deepspeed_enabled:
                    self.reward_funcs[i] = prepare_deepspeed(reward_func, self.accelerator)
                else:
                    # set device placement to True to make `prepare_model` move `reward_func` to device when using fsdp
                    self.reward_funcs[i] = self.accelerator.prepare_model(
                        reward_func, evaluation_mode=True, device_placement=True
                    )

    def _set_signature_columns_if_needed(self):
        # If `self.args.remove_unused_columns` is True, non-signature columns are removed.
        # By default, this method sets `self._signature_columns` to the model's expected inputs (usually, "input_ids"
        # and "attention_mask"). In GRPOTrainer, we preprocess data, so using the model's signature columns doesn't
        # work. Instead, we set them to the columns expected by the `training_step` method, hence the override.
        if self._signature_columns is None:
            self._signature_columns = ["prompt", "image", "images"]

    # This method overrides `Trainer.get_train_dataloader` to support our custom batching strategy.
    # Instead of returning a standard per-step batch (i.e., `per_device_batch_size), our dataloader loads an
    # *generation* batch (i.e., `per_device_batch_size × steps_per_generation`). This allows us to generate completions
    # once every steps_per_generation step—rather than once per accumulation step—which is significantly more
    # efficient. The only change from the original implementation is multiplying the batch size by
    # `steps_per_generation`. Thus, `_prepare_inputs` is called with this *generation* batch, and it handles the
    # splitting internally.
    # Maintenance note: This method is a copy-paste of the original `Trainer.get_train_dataloader` with only one line
    # modification. As a result, some parts of the method aren't relevant to GRPO, but we keep them to stay one line
    # apart from the super method, ensuring easier maintenance in the future.
    def get_train_dataloader(self):
        if self.train_dataset is None:
            raise ValueError("Trainer: training requires a train_dataset.")

        train_dataset = self.train_dataset
        data_collator = self.data_collator
        if is_datasets_available() and isinstance(train_dataset, datasets.Dataset):
            train_dataset = self._remove_unused_columns(train_dataset, description="training")
        else:
            data_collator = self._get_collator_with_removed_columns(data_collator, description="training")

        dataloader_params = {
            "batch_size": self._train_batch_size * self.args.steps_per_generation,  # < this is the change
            "collate_fn": data_collator,
            "num_workers": self.args.dataloader_num_workers,
            "pin_memory": self.args.dataloader_pin_memory,
            "persistent_workers": self.args.dataloader_persistent_workers,
        }

        if not isinstance(train_dataset, torch.utils.data.IterableDataset):
            dataloader_params["sampler"] = self._get_train_sampler()
            dataloader_params["drop_last"] = self.args.dataloader_drop_last
            dataloader_params["worker_init_fn"] = partial(
                seed_worker, num_workers=self.args.dataloader_num_workers, rank=self.args.process_index
            )

            dataloader_params["prefetch_factor"] = self.args.dataloader_prefetch_factor

        return self.accelerator.prepare(DataLoader(train_dataset, **dataloader_params))

    def _get_train_sampler(self, dataset: Dataset | None = None) -> Sampler:
        # Returns a sampler that
        # 1. ensures each prompt is repeated across multiple processes. This guarantees that identical prompts are
        #    distributed to different GPUs, allowing rewards to be computed and normalized correctly within each prompt
        #    group. Using the same seed across processes ensures consistent prompt assignment, preventing discrepancies
        #    in group formation.
        # 2. repeats the batch multiple times to allow reusing generations across multiple updates. Refer to
        #    _prepare_inputs to see how the generations are stored and reused.

        # In the following figure, the values are the prompt indices. The first row shows the first sampled batch, the
        # second row shows the second sampled batch, and so on.
        #
        #                                      |   GPU 0  |   GPU 1  |
        #
        #                 global_step   step    <-───>  num_generations=2
        #                                       <-───────> per_device_train_batch_size=3
        #  grad_accum    ▲  ▲  0          0     0   0   1   1   2   2   <- Generate for the first `steps_per_generation` (prompts 0 to 11); store the completions; use the first slice to compute the loss
        #     =2         ▼  |  0          1     3   3   4   4   5   5   <- Take the stored generations and use the second slice to compute the loss
        #                   |
        #                   |  1          2     6   6   7   7   8   8   <- Take the stored generations and use the third slice to compute the loss
        #  steps_per_gen=4  ▼  1          3     9   9  10  10  11  11   <- Take the stored generations and use the fourth slice to compute the loss
        #
        #                      2          4    12  12  13  13  14  14   <- Generate for the second `steps_per_generation` (prompts 12 to 23); store the completions; use the first slice to compute the loss
        #                      2          5    15  15  16  16  17  17   <- Take the stored generations and use the second slice to compute the loss
        #                                          ...
        if dataset is None:
            dataset = self.train_dataset
        return RepeatSampler(
            data_source=dataset,
            mini_repeat_count=self.num_generations,
            batch_size=self.args.generation_batch_size // self.num_generations,
            repeat_count=self.num_iterations * self.args.steps_per_generation,
            shuffle=self.shuffle_dataset,
            seed=self.args.seed,
        )

    def _get_eval_sampler(self, eval_dataset) -> Sampler:
        # See _get_train_sampler for an explanation of the sampler.
        return RepeatSampler(
            data_source=eval_dataset,
            mini_repeat_count=self.num_generations_eval,
            seed=self.args.seed,
        )

    @profiling_decorator
    def _get_last_hidden_state(
        self,
        unwrapped_model,
        input_ids,
        attention_mask,
        logits_to_keep,
        pixel_values=None,
        image_grid_thw=None,
        pixel_attention_mask=None,
        image_sizes=None,
    ):
        if is_peft_model(unwrapped_model):
            unwrapped_model = unwrapped_model.base_model.model

        # Build model inputs - check if the model supports logits_to_keep (some models and VLMs don't)
        model_inputs = {"input_ids": input_ids, "attention_mask": attention_mask}

        # For Qwen models:
        if image_grid_thw is not None and pixel_values is not None:
            model_inputs["image_grid_thw"] = image_grid_thw
        # For Gemma, SmolVLM2, LLaVa-Next etc.:
        if pixel_values is not None:
            model_inputs["pixel_values"] = pixel_values
        # For SmolVLM2
        if pixel_attention_mask is not None:
            model_inputs["pixel_attention_mask"] = pixel_attention_mask
        # For LLaVa-Next
        if image_sizes is not None:
            model_inputs["image_sizes"] = image_sizes

        # Only add logits_to_keep if the model supports it
        if "logits_to_keep" in self.model_kwarg_keys:
            # We add 1 to `logits_to_keep` because the last logits of the sequence is later excluded
            model_inputs["logits_to_keep"] = logits_to_keep + 1

        model_inputs["use_cache"] = False  # only used in generation; set False to suppress warnings

        last_hidden_state = unwrapped_model.model(**model_inputs).last_hidden_state
        # Exclude the last value: it corresponds to the next token pred
        last_hidden_state = last_hidden_state[:, :-1, :]  # (B, L-1, H)
        # Only keep the last logits_to_keep. For model that support logits_to_keep, this is a no-op.
        last_hidden_state = last_hidden_state[:, -logits_to_keep:, :]  # (B, logits_to_keep, H)
        return last_hidden_state

    def get_high_entropy_mask(self, entropies: torch.Tensor, mask: torch.Tensor, threshold: float) -> torch.Tensor:
        """
        Returns a binary mask identifying tokens whose entropy exceeds a given quantile threshold.

        Args:
            entropies (`torch.Tensor`):
                Tensor of shape (batch_size, seq_len) with per-token entropy values.
            mask (`torch.Tensor`):
                Binary mask of the same shape as `entropies`, where `1` indicates valid tokens and `0` padding.
            threshold (`float`):
                Quantile threshold between `0.0` and `1.0` to select high-entropy tokens.

        Returns:
            `torch.Tensor`:
                Boolean mask of shape (batch_size, seq_len), where `True` indicates tokens with entropy >= threshold
                and `False` otherwise.
        """
        local = entropies[mask.bool()].float()

        # Use a negative pad_value as a sentinel because entropy values are always >= 0.
        # This guarantees that the sentinel cannot collide with any real entropy value.
        pad_value = -1e9

        # Pad across processes so that every rank has the same tensor length
        padded = self.accelerator.pad_across_processes(local, dim=0, pad_index=pad_value)
        gathered = self.accelerator.gather(padded)

        # Drop sentinel values (safe because no entropy can be negative)
        gathered = gathered[gathered != pad_value]

        if gathered.numel() == 0:
            return torch.zeros_like(entropies, dtype=torch.bool)

        entropy_threshold = torch.quantile(gathered, threshold)
        masked_entropies = entropies * mask.float()
        entropy_mask = masked_entropies >= entropy_threshold
        return entropy_mask & mask.bool()  # ensure padding tokens are always masked out

    def _get_per_token_logps_and_entropies(
        self,
        model,
        input_ids,
        attention_mask,
        logits_to_keep,
        batch_size = None,
        compute_entropy = False,
        compute_efficient = False,
        *args,
        **kwargs,
    ):
        # All Unsloth code here in this function is licensed under AGPL3
        # if True: # os.environ.get('UNSLOTH_USE_NEW_MODEL', '0') == '0':
        #     return None, None  # logps, entropies Unsloth efficient GRPO
        if compute_efficient:
            return None, None
        else:
            if not hasattr(self, "_autocast_dtype"):
                self._autocast_dtype = (
                    torch.float16
                    if os.environ.get("ACCELERATE_MIXED_PRECISION", "fp16") == "fp16"
                    else torch.bfloat16
                )
                if os.environ.get("UNSLOTH_FORCE_FLOAT32", "0") == "1":
                    self._autocast_dtype = torch.float16

            pixel_values, image_grid_thw = (
                kwargs.get("pixel_values", None),
                kwargs.get("image_grid_thw", None),
            )
            pixel_attention_mask, image_sizes = (
                kwargs.get("pixel_attention_mask", None),
                kwargs.get("image_sizes", None),
            )

            unwrapped_model = self.accelerator.unwrap_model(
                model, keep_fp32_wrapper = False
            )

            lm_head = self.model.get_output_embeddings().weight

            dtype_bytes = (
                16 if self._autocast_dtype in [torch.float16, torch.bfloat16] else 32
            )
            total_rows = input_ids.shape[0]
            seq_len = input_ids.shape[1]
            hidden_dim = lm_head.shape[1]
            vocab_dim = lm_head.shape[0]

            if self.args.unsloth_grpo_mini_batch is None:
                B, multiplier = autotune_batch_and_chunks(
                    total_rows,
                    seq_len,
                    hidden_dim,
                    vocab_dim,
                    dtype_bytes,
                    self.args.unsloth_logit_chunk_multiplier,
                )
                B = total_rows // B
            else:
                B = self.args.unsloth_grpo_mini_batch

                if self.args.unsloth_logit_chunk_multiplier is None:
                    multiplier = max(4, seq_len // 4096)
                else:
                    multiplier = self.args.unsloth_logit_chunk_multiplier

            all_logprobs_list = []
            if pixel_values is None:
                left_pad_tokens_per_prompt = calculate_pad_tokens_in_prompt(
                    input_ids, logits_to_keep, self.processing_class.pad_token_id
                )
                max_left_pad = torch.max(left_pad_tokens_per_prompt).item()
                input_ids = left_pack_padding(
                    input_ids, self.processing_class.pad_token_id
                )
                attention_mask = input_ids != self.processing_class.pad_token_id
                attention_mask = attention_mask.to(attention_mask.dtype)
            else:
                max_left_pad = 0

            # input_ids_chunks = torch.chunk(input_ids, chunks = B, dim = 0)
            attention_mask_chunks = torch.chunk(attention_mask, chunks = B, dim = 0)

            def chunk_optional(tensor, chunks):
                if tensor is None:
                    return [None] * chunks
                return torch.chunk(tensor, chunks = chunks, dim = 0)

            import math

            total_samples = input_ids.shape[0]
            batch_size = math.ceil(total_samples / B)

            input_ids_chunks = []
            attention_mask_chunks = []
            pixel_values_chunks = []
            image_grid_thw_chunks = []
            pixel_attention_mask_chunks = []

            current_pixel_idx = 0
            # TRL 0.23.0 batching logic
            for start in range(0, total_samples, batch_size):
                end = start + batch_size

                input_ids_chunks.append(input_ids[start:end])
                attention_mask_chunks.append(attention_mask[start:end])

                if image_grid_thw is not None and pixel_values is not None:
                    grid_slice = image_grid_thw[start:end]
                    image_grid_thw_chunks.append(grid_slice)

                    batch_pixel_count = grid_slice.prod(dim = -1).sum().item()

                    start_pixel_idx = current_pixel_idx
                    end_pixel_idx = current_pixel_idx + batch_pixel_count

                    pixel_values_chunks.append(
                        pixel_values[start_pixel_idx:end_pixel_idx]
                    )

                    if pixel_attention_mask is not None:
                        pixel_attention_mask_chunks.append(
                            pixel_attention_mask[start_pixel_idx:end_pixel_idx]
                        )
                    else:
                        pixel_attention_mask_chunks.append(None)

                    current_pixel_idx = end_pixel_idx

                else:
                    pixel_values_chunks.append(None)
                    image_grid_thw_chunks.append(None)
                    pixel_attention_mask_chunks.append(None)

            if image_sizes is not None and not isinstance(image_sizes, torch.Tensor):
                image_sizes_chunks = [[size] for size in image_sizes]
            else:
                image_sizes_chunks = chunk_optional(image_sizes, B)

            temperature = self.temperature
            logit_softcapping = getattr(model.config, "final_logit_softcapping", 0)
            if logit_softcapping is None:
                logit_softcapping = 0
            logit_scale_multiply = getattr(model.config, "logit_scale", 0)
            if logit_scale_multiply is None:
                logit_scale_multiply = 0
            logit_scale_divide = getattr(model.config, "logits_scaling", 0)
            if logit_scale_divide is None:
                logit_scale_divide = 0

            zipped_inputs = zip(
                input_ids_chunks,
                attention_mask_chunks,
                pixel_values_chunks,
                image_grid_thw_chunks,
                pixel_attention_mask_chunks,
                image_sizes_chunks,
            )
            os.environ["UNSLOTH_RETURN_HIDDEN_STATES"] = "1"

            with _get_inference_mode_context_manager(model):
                for (
                    input_ids_chunk,
                    attention_mask_chunk,
                    pixel_values_chunk,
                    image_grid_thw_chunk,
                    pixel_attention_mask_chunk,
                    image_sizes_chunk,
                ) in zipped_inputs:
                    with torch.amp.autocast(
                        device_type = "cuda", dtype = self._autocast_dtype
                    ):
                        if pixel_values is None:
                            logits_chunk = unwrapped_model(
                                input_ids = input_ids_chunk,
                                attention_mask = attention_mask_chunk,
                                pixel_values = pixel_values_chunk,
                                image_grid_thw = image_grid_thw_chunk,
                                pixel_attention_mask = pixel_attention_mask_chunk,
                                image_sizes = image_sizes_chunk,
                            ).logits

                            completion_input_ids_chunk = input_ids_chunk[
                                :, -(logits_to_keep + max_left_pad) :
                            ]
                            logits_chunk = logits_chunk[
                                :, -(logits_to_keep + max_left_pad + 1) :, :
                            ]
                            logits_chunk = logits_chunk[:, :-1, :]
                        else:
                            # Essentially, for VLMs we do not go via the optimized path in models/,
                            # so we don't encounter the Flash Attn left-padding issue.
                            logits_chunk = unwrapped_model(
                                input_ids = input_ids_chunk,
                                attention_mask = attention_mask_chunk,
                                pixel_values = pixel_values_chunk,
                                image_grid_thw = image_grid_thw_chunk,
                                pixel_attention_mask = pixel_attention_mask_chunk,
                                image_sizes = image_sizes_chunk,
                                logits_to_keep = logits_to_keep + 1,
                            ).logits

                            logits_chunk = logits_chunk[:, :-1, :]
                            completion_input_ids_chunk = input_ids_chunk[
                                :, -logits_to_keep:
                            ]

                        logprobs_chunk = chunked_hidden_states_selective_log_softmax(
                            logits_chunk,
                            lm_head,
                            completion_input_ids_chunk,
                            chunks = input_ids_chunk.shape[0] * multiplier,
                            logit_scale_multiply = logit_scale_multiply,
                            logit_scale_divide = logit_scale_divide,
                            logit_softcapping = logit_softcapping,
                            temperature = temperature,
                        )
                    # This is needed to avoid race conditions with GPT OSS offload_embbed=True
                    # However, it seems that this line does not slow down or disrupt models.
                    torch.cuda.synchronize()
                    all_logprobs_list.append(logprobs_chunk)
                logprobs = torch.cat(all_logprobs_list, dim = 0)
                entropies = None

            os.environ["UNSLOTH_RETURN_HIDDEN_STATES"] = "0"

            return logprobs.detach(), entropies  # logps, entropies
            # input_ids = input_ids[:, -logits_to_keep:]
            # For transformers<=4.48, logits_to_keep argument isn't supported, so here we drop logits ourselves.
            # See https://github.com/huggingface/trl/issues/2770
            # logits = logits[:, -logits_to_keep:]
            # return logits
            # See https://huggingface.co/blog/the_n_implementation_details_of_rlhf_with_ppo#policy-training-implementation-details
            # logits = logits / self.temperature
            # logps = selective_log_softmax(logits, input_ids)

            # row_indices, col_indices = torch.where(logps < -20)

            # # Method 1: Check if tensors have elements
            # if len(row_indices) > 0 and len(col_indices) > 0:
            #     breakpoint()  # Breakpoint triggered here
            #     print("Found high values!")
            # return  logps #  compute logprobs for the input tokens

    def _fix_param_name_to_vllm(self, name, extra_prefixes: list[str] | None = None):
        extra_prefixes = extra_prefixes or []
        prefixes = ["_checkpoint_wrapped_module."] + extra_prefixes
        for prefix in prefixes:
            name = name.replace(prefix, "")
        return name

    def _sync_fsdp1_params_to_vllm(self, module: nn.Module, prefix: str = "", visited=None):
        """Memory-efficient post-order traversal of FSDP modules to extract full parameters and sync with vLLM."""
        # For FSDP1, we need to recurse into children and also use summon_full_params
        if visited is None:
            visited = set()
        for child_name, child_module in module.named_children():
            child_prefix = f"{prefix}.{child_name}" if prefix else child_name
            self._sync_fsdp1_params_to_vllm(
                child_module, prefix=child_prefix, visited=visited
            )  # recurse into the child

        if isinstance(module, FSDP):
            with FSDP.summon_full_params(module, recurse=False, writeback=False):
                for param_name, param in module.named_parameters():
                    full_name = f"{prefix}.{param_name}" if prefix else param_name
                    full_name = self._fix_param_name_to_vllm(full_name, extra_prefixes=["_fsdp_wrapped_module."])

                    if full_name in visited:
                        continue  # skip FSDP subtrees already traversed
                    visited.add(full_name)

                    if self.vllm_mode == "server" and self.accelerator.is_main_process:
                        self.vllm_client.update_named_param(full_name, param.data)
                    elif self.vllm_mode == "colocate":

                        pass

                        pass

    def _sync_fsdp2_params_to_vllm(self, module: nn.Module):
        # For FSDP2, module already covers all parameters, so no need for recursion
        for name, param in module.items():
            # When using PEFT, we need to recover the original parameter name
            name = name.removeprefix("base_model.model.").replace(".base_layer", "")
            # Skip PEFT layers: they don’t exist in vLLM, and they are merged already.
            if is_peft_model(module) and module.prefix in name:
                continue
            # When module to save, remove its prefix and discard the original module
            if "original_module" in name:
                continue
            name = self._fix_param_name_to_vllm(name, extra_prefixes=["modules_to_save.default."])

            if param.is_cpu:
                param = param.to(torch.device("cuda"))
            param = param.full_tensor()

            if self.vllm_mode == "server" and self.accelerator.is_main_process:
                self.vllm_client.update_named_param(name, param)
            elif self.vllm_mode == "colocate":

                pass

                pass

    def _move_model_to_vllm(self, *args, **kwargs):
        return None

    def training_step(self, model, inputs, num_items_in_batch):
        time_before = time.perf_counter()
        output = super().training_step(model, inputs, num_items_in_batch)
        self._step += 1
        time_after = time.perf_counter()
        self._current_train_step_time += time_after - time_before
        if self._step % self.current_gradient_accumulation_steps == 0:
            self._metrics["train"]["step_time"].append(self._current_train_step_time)
            self._current_train_step_time = 0.0
        return output

    @profiling_decorator
    def _prepare_inputs(self, generation_batch: dict[str, torch.Tensor | Any]) -> dict[str, torch.Tensor | Any]:
        # Prepares inputs for model training/evaluation by managing completion generation and batch handling.
        # During training:
        #   - Receives the local generation batch (Per-GPU batch size × steps per generation)
        #     from the modified training dataloader instead of the standard local batch
        #   - Generates completions once for the entire generation batch and splits it into batches of size
        #     `per_device_train_batch_size`
        #   - Buffers these completions and returns the appropriate slice for the current accumulation step
        #   - Optimizes by regenerating completions only periodically (every steps_per_generation * num_iterations)
        # During evaluation:
        #   - The input is treated as a standard local batch (no accumulation, no multiple iterations)
        #   - Completions are generated for each batch without buffering or reuse
        # Returns a single local batch in both cases.

        mode = "train" if self.model.training else "eval"
        if mode == "train":
            generate_every = self.args.steps_per_generation * self.num_iterations
            if self._step % generate_every == 0 or self._buffered_inputs is None:
                # self._buffered_inputs=None can occur when resuming from a checkpoint
                generation_batch = self._generate_and_score_completions(generation_batch)
                generation_batch = split_pixel_values_by_grid(generation_batch)

                try: generation_batch = shuffle_sequence_dict(generation_batch)

                except: pass
                generation_batches = split_tensor_dict(generation_batch, self.args.steps_per_generation)
                self._buffered_inputs = [unsplit_pixel_values_by_grid(batch) for batch in generation_batches]
            inputs = self._buffered_inputs[self._step % self.args.steps_per_generation]
        else:
            # In evaluation, there is neither batch grouping for generation, nor multiple iterations, hence
            # local generation batch == local eval batch
            inputs = self._generate_and_score_completions(generation_batch)
        return inputs

    @profiling_decorator
    def _calculate_rewards(self, inputs, prompts, completions, completion_ids_list):
        device = self.accelerator.device
        rewards_per_func = torch.zeros(len(prompts), len(self.reward_funcs), device=device)

        # Repeat all input columns (but "prompt", "completion", and "completion_ids") to match the num of generations
        keys = [key for key in inputs[0] if key not in ["prompt", "completion", "completion_ids"]]
        reward_kwargs = {key: [example[key] for example in inputs] for key in keys}

        # This allows for dynamic reward shaping based on training progress.
        reward_kwargs["trainer_state"] = self.state

        async_funcs_info = []  # async custom functions for asyncio.gather

        for i, (reward_func, reward_processing_class, reward_func_name) in enumerate(
            zip(self.reward_funcs, self.reward_processing_classes, self.reward_func_names, strict=True)
        ):
            if isinstance(reward_func, nn.Module):  # Module (no PretrainedModel) for compat with compiled models
                with profiling_context(self, reward_func_name):
                    if is_conversational(inputs[0]):
                        messages = [{"messages": p + c} for p, c in zip(prompts, completions, strict=True)]
                        texts = [
                            apply_chat_template(x, reward_processing_class, **self.chat_template_kwargs)["text"]
                            for x in messages
                        ]
                    else:
                        texts = [p + c for p, c in zip(prompts, completions, strict=True)]
                    reward_inputs = reward_processing_class(
                        text=texts, return_tensors="pt", padding=True, padding_side="right", add_special_tokens=False
                    )
                    reward_inputs = super()._prepare_inputs(reward_inputs)
                    with torch.inference_mode():
                        rewards_per_func[:, i] = reward_func(**reward_inputs).logits[:, 0]  # Shape (B*G,)
            elif asyncio.iscoroutinefunction(reward_func):  # Separate async reward funcs to run them in parallel later
                async_funcs_info.append((i, reward_func, reward_func_name))
            else:
                # Run synchronous reward function
                with profiling_context(self, reward_func_name):
                    output_reward_func = reward_func(
                        prompts=prompts, completions=completions, completion_ids=completion_ids_list, **reward_kwargs
                    )
                    # Convert None values to NaN
                    output_reward_func = [reward if reward is not None else torch.nan for reward in output_reward_func]
                    rewards_per_func[:, i] = torch.tensor(output_reward_func, dtype=torch.float32, device=device)

        # Execute async custom functions in parallel using asyncio.gather
        if async_funcs_info:

            async def _invoke_async_reward(index, func, func_name):
                with profiling_context(self, func_name):
                    output = await func(
                        prompts=prompts, completions=completions, completion_ids=completion_ids_list, **reward_kwargs
                    )
                    output = [r if r is not None else torch.nan for r in output]
                    return index, output

            async def _run_async_funcs():
                coros = [_invoke_async_reward(i, func, func_name) for (i, func, func_name) in async_funcs_info]
                return await asyncio.gather(*coros)

            async_results = asyncio.run_coroutine_threadsafe(_run_async_funcs(), self.async_reward_loop).result()
            for idx, output_reward_func in async_results:
                rewards_per_func[:, idx] = torch.tensor(output_reward_func, dtype=torch.float32, device=device)

        # If all reward functions return None for a given row, issue a detailed warning
        if torch.isnan(rewards_per_func).all(dim=1).any():
            nan_row_idx = torch.isnan(rewards_per_func).all(dim=1).nonzero(as_tuple=True)[0][0]
            row_reward_kwargs = {
                key: value[nan_row_idx] for key, value in reward_kwargs.items() if key != "trainer_state"
            }
            row_reward_kwargs["prompt"] = prompts[nan_row_idx]
            row_reward_kwargs["completion"] = completions[nan_row_idx]
            logger.warning(
                f"All reward functions returned None for the following kwargs:\n{row_reward_kwargs}\n"
                "Please ensure that at least one reward function returns a valid reward."
            )

        # Gather the reward per function: this part is crucial, because the rewards are normalized per group and the
        # completions may be distributed across processes
        rewards_per_func = gather(rewards_per_func)
        return rewards_per_func

    def _generate_single_turn(self, prompts: list):
        device = self.accelerator.device
        mode = "train" if self.model.training else "eval"

        # Generate completions using either vLLM or regular generation
        if self.use_vllm:
            if self.vllm_mode == "colocate" and self.args.vllm_enable_sleep_mode:
                # wake up colocated vLLM instances if needed
                torch.cuda.empty_cache()  # required to avoid OOM in some cases
                self.llm.wake_up(tags=["weights"])
                # Work around for https://github.com/vllm-project/vllm/issues/29341
                

            # First, update the vLLM weights if needed
            if self.state.global_step != self._last_loaded_step:
                self._move_model_to_vllm()
                self._last_loaded_step = self.state.global_step

            if is_conversational({"prompt": prompts[0]}):
                prompts = [prepare_multimodal_messages_vllm(prompt) for prompt in prompts]

            # In vLLM, tool call arguments must be JSON strings. See https://github.com/vllm-project/vllm/pull/28820
            for prompt in prompts:  # iterate over each conversation
                if is_conversational({"prompt": prompt}):
                    for message in prompt:  # iterate over each message
                        if "tool_calls" in message:  # check if message has tool calls
                            for call in message["tool_calls"]:
                                args = call["function"]["arguments"]
                                if isinstance(args, dict):  # only convert dict → JSON string
                                    call["function"]["arguments"] = json.dumps(args)

            # Generate completions using vLLM: gather all prompts and use them in a single call in the main process
            if self.vllm_mode == "server":
                all_prompts = gather_object(prompts)
                num_generations = self.num_generations if mode == "train" else self.num_generations_eval

                if self.accelerator.is_main_process:
                    # Since 'prompts' contains 'num_generations' duplicates, we first take unique prompts, and generate
                    # num_generations outputs for each one. This is faster than generating outputs for each duplicate
                    # prompt individually.
                    ordered_set_of_prompts = all_prompts[::num_generations]

                    sampling_params = {
                        "n": num_generations,
                        "repetition_penalty": self.repetition_penalty,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "min_p": 0.0 if self.min_p is None else self.min_p,
                        "max_tokens": self.max_completion_length,
                        "structured_outputs_regex": self.structured_outputs_regex,
                        "generation_kwargs": self.args.generation_kwargs,
                    }
                    with profiling_context(self, "vLLM.generate"):
                        if self.rollout_func is not None:
                            rollout_prompts = ordered_set_of_prompts
                            if rollout_prompts and is_conversational({"prompt": rollout_prompts[0]}):
                                rollout_prompts = [
                                    apply_chat_template(
                                        {"prompt": p}, self.processing_class, **self.chat_template_kwargs
                                    )["prompt"]
                                    for p in rollout_prompts
                                ]
                            output = self.rollout_func(rollout_prompts, self)
                        else:
                            if is_conversational({"prompt": ordered_set_of_prompts[0]}):
                                output = self.vllm_client.chat(
                                    messages=ordered_set_of_prompts,
                                    **sampling_params,
                                    chat_template_kwargs=self.chat_template_kwargs,
                                    tools=self.tools,
                                    chat_template=self.chat_template,
                                )
                            else:
                                output = self.vllm_client.generate(prompts=ordered_set_of_prompts, **sampling_params)
                        # Extract required fields and collect any extra fields for reward functions
                        required_keys = {"prompt_ids", "completion_ids", "logprobs"}
                        extra_fields = {k: v for k, v in output.items() if k not in required_keys}
                        payload = (output["prompt_ids"], output["completion_ids"], output["logprobs"], extra_fields)
                else:
                    payload = None

                # Broadcast the completions from the main process to all processes, ensuring each process receives its corresponding slice.
                obj_list = [payload]
                broadcast_object_list(obj_list, from_process=0)
                all_prompt_ids, all_completion_ids, all_logprobs, all_extra_fields = obj_list[0]

                # At this point, we only get 1 copy of each prompt, so we need to repeat them num_generations times
                all_prompt_ids = [ids for ids in all_prompt_ids for _ in range(num_generations)]

                process_slice = slice(
                    self.accelerator.process_index * len(prompts),
                    (self.accelerator.process_index + 1) * len(prompts),
                )
                prompt_ids = all_prompt_ids[process_slice]
                completion_ids = all_completion_ids[process_slice]
                logprobs = all_logprobs[process_slice]

                # Slice extra fields dict-of-lists per process (extra fields are per-completion, like completion_ids)
                extra_fields = {}
                for key, values in all_extra_fields.items():
                    if isinstance(values, list):
                        extra_fields[key] = values[process_slice]
                    else:
                        extra_fields[key] = values

            # Generate completions using colocated vLLM instances: each device holds vLLM copy and work on their own batch of prompts
            elif self.vllm_mode == "colocate":
                if self.rollout_func is not None:
                    rollout_prompts = prompts
                    if rollout_prompts and is_conversational({"prompt": rollout_prompts[0]}):
                        rollout_prompts = [
                            apply_chat_template(
                                {"prompt": prompt}, self.processing_class, **self.chat_template_kwargs
                            )["prompt"]
                            for prompt in rollout_prompts
                        ]
                    output = self.rollout_func(rollout_prompts, self)
                    required_keys = {"prompt_ids", "completion_ids", "logprobs"}
                    extra_fields = {k: v for k, v in output.items() if k not in required_keys}
                    prompt_ids = output["prompt_ids"]
                    completion_ids = output["completion_ids"]
                    logprobs = output["logprobs"]
                else:
                    if Version(vllm.__version__) <= Version("0.10.2"):
                        structured_outputs_key = "guided_decoding"
                        if self.structured_outputs_regex:
                            structured_outputs = GuidedDecodingParams(regex=self.structured_outputs_regex)
                        else:
                            structured_outputs = None
                    else:
                        structured_outputs_key = "structured_outputs"
                        if self.structured_outputs_regex:
                            structured_outputs = StructuredOutputsParams(regex=self.structured_outputs_regex)
                        else:
                            structured_outputs = None

                    generation_kwargs = {
                        "n": 1,  # vLLM on each GPU generates only 1 in colocate mode
                        "repetition_penalty": self.repetition_penalty,
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "top_k": self.top_k,
                        "min_p": 0.0 if self.min_p is None else self.min_p,
                        "max_tokens": self.max_completion_length,
                        "logprobs": 0,  # enable returning log probabilities; 0 means for the sampled tokens only
                    }
                    generation_kwargs[structured_outputs_key] = structured_outputs
                    if self.args.generation_kwargs is not None:
                        generation_kwargs.update(self.args.generation_kwargs)
                    sampling_params = SamplingParams(**grpo_update_SamplingParams(SamplingParams, generation_kwargs, getattr(self.args, 'vllm_sampling_params', None)))

                    if self.vllm_tensor_parallel_size > 1:
                        # Gather prompts from all ranks in the TP group and flatten.
                        # Each rank starts with its own prompts; after gathering, all ranks see the full group set.
                        orig_size = len(prompts)
                        gathered_prompts = [None for _ in range(self.vllm_tensor_parallel_size)]
                        torch.distributed.all_gather_object(gathered_prompts, prompts, group=self.tp_group)
                        all_prompts = [p for sublist in gathered_prompts for p in sublist]
                    else:
                        all_prompts = prompts

                    if self.args.vllm_enable_sleep_mode:
                        self.llm.wake_up(tags=["kv_cache"])

                    with profiling_context(self, "vLLM.generate"):
                        if is_conversational({"prompt": prompts[0]}):
                            all_outputs = self.llm.chat(
                                all_prompts,
                                sampling_params=sampling_params,
                                use_tqdm=False,
                                chat_template_kwargs=self.chat_template_kwargs,
                                tools=self.tools,
                                chat_template=self.chat_template, lora_request = self.model.load_lora('grpo_trainer_lora_model', load_tensors = True))
                        else:
                            all_outputs = self.llm.generate(
                                all_prompts, sampling_params=sampling_params, use_tqdm=False, lora_request = self.model.load_lora('grpo_trainer_lora_model', load_tensors = True))

                    all_prompt_ids = [output.prompt_token_ids for output in all_outputs]
                    all_completion_ids = [output.token_ids for outputs in all_outputs for output in outputs.outputs]
                    all_logprobs = [
                        [next(iter(lp.values())).logprob for lp in output.logprobs]
                        for outputs in all_outputs
                        for output in outputs.outputs
                    ]

                    if self.vllm_tensor_parallel_size > 1:
                        # Slice completions for this rank within its TP group.
                        # Each rank generates all outputs — we keep only our share.
                        local_rank_in_group = torch.distributed.get_rank(group=self.tp_group)
                        tp_slice = slice(local_rank_in_group * orig_size, (local_rank_in_group + 1) * orig_size)
                        prompt_ids = all_prompt_ids[tp_slice]
                        completion_ids = all_completion_ids[tp_slice]
                        logprobs = all_logprobs[tp_slice]
                    else:
                        prompt_ids = all_prompt_ids
                        completion_ids = all_completion_ids
                        logprobs = all_logprobs

                    extra_fields = {}  # No extra fields for colocate mode

                    if self.args.vllm_enable_sleep_mode:
                        self.llm.sleep(level=2)

        elif self.use_transformers_paged:
            if is_conversational({"prompt": prompts[0]}):
                processor_outputs = self.processing_class.apply_chat_template(
                    conversation=prompts,
                    tools=self.tools,
                    chat_template=self.chat_template,
                    add_generation_prompt=True,
                    tokenize=True,
                    return_dict=True,
                    **self.chat_template_kwargs,
                )
            else:
                processor_outputs = self.processing_class(text=prompts)

            with (
                profiling_context(self, "transformers.generate_batch"),
                unwrap_model_for_generation(
                    self.model_wrapped, self.accelerator, gather_deepspeed3_params=self.args.ds3_gather_for_generation
                ) as unwrapped_model,
                torch.no_grad(),
                FSDP.summon_full_params(self.model_wrapped, recurse=False) if self.is_fsdp_enabled else nullcontext(),
            ):
                # Cast to the appropriate dtype based on training configuration
                if self.args.bf16:
                    unwrapped_model.to(torch.bfloat16)
                elif self.args.fp16:
                    unwrapped_model.to(torch.float16)
                if self.args.cast_lm_head_to_fp32:
                    unwrapped_model.lm_head.to(torch.float32)
                with torch.inference_mode():
                    # Continuous batching API expects 'inputs' arg only
                    all_outputs = unwrapped_model.generate_batch(
                        processor_outputs["input_ids"], generation_config=self.generation_config, progress_bar=False
                    )
                    unwrapped_model.train()  # restore training mode, as generate_batch forces eval mode
            completion_ids = [output.generated_tokens for output in all_outputs.values()]
            prompt_ids = processor_outputs["input_ids"]
            logprobs = None  # not used in this case
            extra_fields = {}  # No extra fields for paged mode

        else:
            # Regular generation path
            if is_conversational({"prompt": prompts[0]}):
                generate_inputs = self.processing_class.apply_chat_template(
                    conversation=prompts,
                    tools=self.tools,
                    chat_template=self.chat_template,
                    add_generation_prompt=True,
                    tokenize=True,
                    padding=True,
                    padding_side="left",
                    return_tensors="pt",
                    return_dict=True,
                    **self.chat_template_kwargs,
                )
            else:
                generate_inputs = self.processing_class(
                    text=prompts, padding=True, padding_side="left", return_tensors="pt"
                )
            generate_inputs = super()._prepare_inputs(generate_inputs)

            with (
                profiling_context(self, "transformers.generate"),
                unwrap_model_for_generation(
                    self.model_wrapped,
                    self.accelerator,
                    gather_deepspeed3_params=self.args.ds3_gather_for_generation,
                    generation_kwargs=self.generation_kwargs,  # Override model.generation_config with generation_kwargs to fix transformers#42762
                ) as unwrapped_model,
                torch.no_grad(),
                FSDP.summon_full_params(self.model_wrapped, recurse=False) if self.is_fsdp_enabled else nullcontext(),
            ):
                prompt_completion_ids = unwrapped_model.generate(
                    **generate_inputs, generation_config=self.generation_config, disable_compile=True
                )
            # Compute prompt length and extract completion ids
            prompt_ids, prompt_mask = generate_inputs["input_ids"], generate_inputs["attention_mask"]
            prompt_length = prompt_ids.size(1)
            completion_ids = prompt_completion_ids[:, prompt_length:]

            # Mask everything after the first EOS token
            is_eos = completion_ids == self.eos_token_id
            eos_idx = torch.full((is_eos.size(0),), is_eos.size(1), dtype=torch.long, device=device)
            eos_idx[is_eos.any(dim=1)] = is_eos.int().argmax(dim=1)[is_eos.any(dim=1)]
            sequence_indices = torch.arange(is_eos.size(1), device=device).expand(is_eos.size(0), -1)
            completion_mask = (sequence_indices <= eos_idx.unsqueeze(1)).int()
            prompt_ids = [p[m].tolist() for p, m in zip(prompt_ids, prompt_mask.bool(), strict=True)]
            completion_ids = [c[m].tolist() for c, m in zip(completion_ids, completion_mask.bool(), strict=True)]
            logprobs = None  # not used in this case
            extra_fields = {}  # No extra fields for non-rollout_func paths

        return prompt_ids, completion_ids, logprobs, extra_fields

    def _tool_call_loop(self, prompts, prompt_ids, completion_ids, completions, logprobs):
        # Tool execution loop: execute tools, then regenerate completions with tool results appended to the prompt
        tool_calls = [completion[0].get("tool_calls") for completion in completions]
        idxs_with_tool = [idx for idx, tool_call in enumerate(tool_calls) if tool_call]
        tool_calls = [tool_calls[idx] for idx in idxs_with_tool]
        tool_mask = [[1] * len(ids) for ids in completion_ids]  # 0 for tool result tokens, 1 elsewhere
        tool_call_count = 0
        tool_failure_count = 0
        iteration_num = 0
        while idxs_with_tool and iteration_num < self.max_tool_calling_iterations:
            prompt_completion_tools = [prompts[i] for i in idxs_with_tool]  # select only prompts that need tool calls

            # Call the tools, and build the new prompt for generation
            for idx in range(len(idxs_with_tool)):
                idx_with_tool = idxs_with_tool[idx]
                tool_call_list = tool_calls[idx]
                prompt_completion_tool = prompt_completion_tools[idx]
                # Append the last assistant message (which triggered tool_calls) to the prompt
                prompt_completion_tool.append(completions[idx_with_tool][-1])
                for tool_call in tool_call_list:
                    tool_call_count += 1
                    if tool_call["type"] == "function":
                        function = tool_call["function"]
                        name = function["name"]
                        try:
                            result = self._tool_dict[name](**function["arguments"])
                        except Exception as e:
                            tool_failure_count += 1
                            result = {"error": str(e)}
                    else:
                        tool_failure_count += 1
                        name = tool_call.get("name", "unknown")
                        result = {"error": f"Unsupported tool call type: {tool_call['type']}"}
                    tool_message = {"role": "tool", "name": name, "content": str(result)}
                    prompt_completion_tool.append(tool_message)
                    completions[idx_with_tool].append(tool_message)

            # Tokenize and filter samples whose length exceeds max allowed length. This is important, because both
            # vLLM and transformers will error out if the input is longer than the model's max length.
            pct_ids = self.processing_class.apply_chat_template(
                prompt_completion_tools,
                tools=self.tools,
                chat_template=self.chat_template,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=False,
                **self.chat_template_kwargs,
            )
            if self.use_vllm and self.vllm_mode == "colocate":
                max_model_len = self.llm.llm_engine.model_config.max_model_len
            elif not self.use_vllm:
                max_model_len = self.model.config.max_position_embeddings
            else:
                raise NotImplementedError(
                    f"Unsupported mode detected: use_vllm={self.use_vllm}, vllm_mode={self.vllm_mode}"
                )
            overlong = [len(pct) >= max_model_len for pct in pct_ids]
            for idx in range(len(idxs_with_tool)):
                idx_with_tool = idxs_with_tool[idx]
                if overlong[idx]:
                    prompt_length = len(prompt_ids[idx_with_tool])
                    ct = pct_ids[idx][prompt_length : prompt_length + self.max_completion_length]
                    completion_ids[idx_with_tool] = ct
                    tool_mask[idx_with_tool] += [1] * (len(ct) - len(tool_mask[idx_with_tool]))
                    if logprobs is not None:
                        logprobs[idx_with_tool] += [0.0] * (len(ct) - len(logprobs[idx_with_tool]))
            # Keep only non-overlong items for further processing
            idxs_with_tool = [idx for idx, o in zip(idxs_with_tool, overlong, strict=True) if not o]
            prompt_completion_tools = [pct for pct, o in zip(prompt_completion_tools, overlong, strict=True) if not o]
            if not idxs_with_tool:
                break  # all overlong, exit tool loop

            # Generate new completions after tool execution
            prompt_completion_tool_ids, post_tool_ids, post_tool_logprobs, _ = self._generate_single_turn(
                prompt_completion_tools
            )

            # Sanity check: from experience, this is useful to catch bugs in the chat template
            for idx in range(len(idxs_with_tool)):
                idx_with_tool = idxs_with_tool[idx]
                pct = prompt_completion_tool_ids[idx]  # = prompt-completion-tool
                if prompt_ids[idx_with_tool] != pct[: len(prompt_ids[idx_with_tool])]:
                    raise ValueError(
                        "The chat template is not prefix-preserving. Please update it to use a prefix-preserving "
                        "format."
                    )

            # Truncate so that pct[len(prompt_ids[idx]) :] + post_tool does not exceed max_completion_length
            for idx in range(len(idxs_with_tool)):
                idx_with_tool = idxs_with_tool[idx]
                prompt_len = len(prompt_ids[idx_with_tool])
                completion_tool_ids = prompt_completion_tool_ids[idx][prompt_len:]
                excess_length = len(completion_tool_ids) + len(post_tool_ids[idx]) - self.max_completion_length
                if excess_length > 0:
                    # If exceeding max length, truncate post_tool_ids
                    post_tool_ids[idx] = post_tool_ids[idx][:-excess_length]
                    if logprobs is not None:
                        post_tool_logprobs[idx] = post_tool_logprobs[idx][:-excess_length]
                    excess_length = len(completion_tool_ids) + len(post_tool_ids[idx]) - self.max_completion_length
                    if excess_length > 0:
                        # If still exceeding max length, truncate completion_tool_ids as well
                        prompt_completion_tool_ids[idx] = prompt_completion_tool_ids[idx][:-excess_length]

            # Update tool_mask: the tool result should be 0 and the post-tool 1
            for idx in range(len(idxs_with_tool)):
                idx_with_tool = idxs_with_tool[idx]
                prompt_completion_tool_length = len(prompt_completion_tool_ids[idx])
                prompt_length = len(prompt_ids[idx_with_tool])
                completion_length = len(completion_ids[idx_with_tool])
                post_tool_length = len(post_tool_ids[idx])
                tool_length = prompt_completion_tool_length - prompt_length - completion_length
                tool_mask[idx_with_tool] += [0] * tool_length + [1] * post_tool_length
                if logprobs is not None:
                    logprobs[idx_with_tool] += [0.0] * tool_length + post_tool_logprobs[idx]

            # Update completion_ids with the new completions (after tool execution)
            for idx in range(len(idxs_with_tool)):
                idx_with_tool = idxs_with_tool[idx]
                prompt_length = len(prompt_ids[idx_with_tool])
                pct = prompt_completion_tool_ids[idx]  # = prompt-completion-tool
                completion_ids[idx_with_tool] = pct[prompt_length:] + post_tool_ids[idx]

            # Decode post-tool completions
            post_tool_completions = [
                parse_response(self.processing_class, ids) if ids else {} for ids in post_tool_ids
            ]

            # Add post-tool completions to the existing completions
            for idx in range(len(idxs_with_tool)):
                idx_with_tool = idxs_with_tool[idx]
                if post_tool_completions[idx]:  # {} if post-tool completions completely truncated
                    completions[idx_with_tool].append(post_tool_completions[idx])

            # Check for further tool calls
            tool_calls = [completion.get("tool_calls") for completion in post_tool_completions]
            idxs_with_tool = [idx for idx, tool_call in zip(idxs_with_tool, tool_calls, strict=True) if tool_call]
            tool_calls = [tool_call for tool_call in tool_calls if tool_call]
            iteration_num += 1
        return tool_mask, completions, completion_ids, logprobs, tool_call_count, tool_failure_count

    def _generate(self, prompts: list):
        device = self.accelerator.device
        mode = "train" if self.model.training else "eval"

        # Copy the prompts to avoid modifying the original list
        prompts = copy.deepcopy(prompts)

        prompt_ids, completion_ids, logprobs, extra_fields = self._generate_single_turn(prompts)

        # Decode completions. It's important to use `parse_response` when possible, because it handles tool calls.
        if is_conversational({"prompt": prompts[0]}):
            if (
                Version(transformers.__version__) >= Version("5.0.0.dev0")  # parse_response added in v5
                and isinstance(self.processing_class, PreTrainedTokenizerBase)  # doesn't work with processors
                and hasattr(self.processing_class, "response_schema")  # attribute not set by default for now
                and self.processing_class.response_schema is not None  # only works if the tokenizer has a schema
            ):
                completions = [[parse_response(self.processing_class, ids)] for ids in completion_ids]
            else:
                contents = self.processing_class.batch_decode(completion_ids, skip_special_tokens=True)
                completions = [[{"role": "assistant", "content": content}] for content in contents]
        else:
            completions = self.processing_class.batch_decode(completion_ids, skip_special_tokens=True)

        # Extract tool calls from the completions and (possibly) execute them
        if self.tools:
            (
                tool_mask,
                completions,
                completion_ids,
                logprobs,
                tool_call_count,
                tool_failure_count,
            ) = self._tool_call_loop(prompts, prompt_ids, completion_ids, completions, logprobs)
        else:
            tool_mask = None

        # Get completion length per sequence, used for logging
        prompt_lengths = torch.tensor([len(ids) for ids in prompt_ids], device=device)
        if tool_mask is not None:  # count only non-tool tokens (tool_mask=1)
            completion_lengths = torch.tensor([sum(mask) for mask in tool_mask], device=device)
        else:
            completion_lengths = torch.tensor([len(ids) for ids in completion_ids], device=device)
        agg_prompt_lengths = self.accelerator.gather(prompt_lengths)
        agg_completion_lengths = self.accelerator.gather(completion_lengths)
        total_prompt_tokens = agg_prompt_lengths.sum()
        total_completion_tokens = agg_completion_lengths.sum()  # = num_items_in_batch, required for the DAPO loss

        # Log the metrics
        if mode == "train":
            self.state.num_input_tokens_seen += (total_prompt_tokens + total_completion_tokens).item()
        self._metrics[mode]["num_tokens"] = [self.state.num_input_tokens_seen]

        # Log completion lengths, mean, min, max
        self._metrics[mode]["completions/mean_length"].append(agg_completion_lengths.float().mean().item())
        self._metrics[mode]["completions/min_length"].append(agg_completion_lengths.float().min().item())
        self._metrics[mode]["completions/max_length"].append(agg_completion_lengths.float().max().item())

        # Identify sequences that terminated with EOS and log their lengths
        eos_and_pad = [self.eos_token_id, self.pad_token_id]
        is_truncated = torch.tensor([ids[-1] not in eos_and_pad for ids in completion_ids], device=device)
        agg_is_truncated = self.accelerator.gather(is_truncated)
        self._metrics[mode]["completions/clipped_ratio"].append(agg_is_truncated.float().mean().item())
        term_completion_lengths = agg_completion_lengths[~agg_is_truncated]
        if len(term_completion_lengths) == 0:  # edge case where no terminated sequences are found
            term_completion_lengths = torch.zeros(1, device=device)
        self._metrics[mode]["completions/mean_terminated_length"].append(term_completion_lengths.float().mean().item())
        self._metrics[mode]["completions/min_terminated_length"].append(term_completion_lengths.float().min().item())
        self._metrics[mode]["completions/max_terminated_length"].append(term_completion_lengths.float().max().item())

        if self.tools:
            agg_tool_call_count = self.accelerator.gather(torch.tensor(tool_call_count, device=device)).sum()
            tool_call_frequency = (agg_tool_call_count / len(agg_prompt_lengths)).item()
            self._metrics[mode]["tools/call_frequency"].append(tool_call_frequency)
            agg_tool_failure_count = self.accelerator.gather(torch.tensor(tool_failure_count, device=device)).sum()
            failure_frequency = (
                (agg_tool_failure_count / agg_tool_call_count).item() if agg_tool_call_count > 0 else 0.0
            )
            self._metrics[mode]["tools/failure_frequency"].append(failure_frequency)

        return (
            prompt_ids,
            completion_ids,
            tool_mask,
            completions,
            total_completion_tokens,
            logprobs,
            extra_fields,
        )

    def _generate_and_score_completions(
        self, inputs: list[dict[str, torch.Tensor | Any]]
    ) -> dict[str, torch.Tensor | Any]:
        device = self.accelerator.device
        mode = "train" if self.model.training else "eval"

        prompts = [x["prompt"] for x in inputs]

        if "images" in inputs[0]:
            images = [example.get("images") for example in inputs]
        elif "image" in inputs[0]:
            images = [[example.get("image")] if example.get("image") is not None else None for example in inputs]
        else:
            images = None
        # Transformers requires at least one image in the batch, otherwise it throws an error
        if images is not None and all(img_list == [] for img_list in images):
            images = None

        # If the prompts are conversational and the inputs contain images, we need to convert the prompts from
        # [{"role": "user", "content": "What color is the sky?"}] to
        # [{"role": "user", "content": [{"type": "image", "image": <Image>}, {"type": "text", "text": "What color is the sky?"}]}]
        if images is not None:
            prompts = [
                prepare_multimodal_messages(prompt, image_list)
                for prompt, image_list in zip(prompts, images, strict=True)
            ]

        (
            prompt_ids_list,
            completion_ids_list,
            tool_mask_list,
            completions,
            num_items_in_batch,
            sampling_per_token_logps_list,
            extra_fields,
        ) = self._generate(prompts)

        # Convert lists of token IDs to padded tensors
        prompt_ids = [torch.tensor(ids, device=device) for ids in prompt_ids_list]
        prompt_mask = [torch.ones_like(ids, dtype=torch.long) for ids in prompt_ids]
        prompt_ids = pad(prompt_ids, padding_value=self.pad_token_id, padding_side="left")
        prompt_mask = pad(prompt_mask, padding_value=0, padding_side="left")
        completion_ids = [torch.tensor(ids, device=device) for ids in completion_ids_list]
        completion_mask = [torch.ones_like(ids, dtype=torch.long) for ids in completion_ids]
        completion_ids = pad(completion_ids, padding_value=self.pad_token_id, padding_side="right")
        completion_mask = pad(completion_mask, padding_value=0, padding_side="right")
        if sampling_per_token_logps_list is not None:
            sampling_per_token_logps = [torch.tensor(logps, device=device) for logps in sampling_per_token_logps_list]
            sampling_per_token_logps = pad(sampling_per_token_logps, padding_value=0.0, padding_side="right")
        else:
            sampling_per_token_logps = None
        if self.tools:
            tool_mask = [torch.tensor(mask, device=device) for mask in tool_mask_list]
            tool_mask = pad(tool_mask, padding_value=1, padding_side="right")  # 0 for tool result tokens, 1 elsewhere

        # If mask_truncated_completions is enabled, zero out truncated completions in completion_mask
        if self.mask_truncated_completions:
            eos_and_pad = [self.eos_token_id, self.pad_token_id]
            is_truncated = torch.tensor([ids[-1] not in eos_and_pad for ids in completion_ids_list], device=device)
            completion_mask = completion_mask * (~is_truncated).unsqueeze(1).int()

        # Concatenate prompt_mask with completion_mask for logit computation
        prompt_completion_ids = torch.cat([prompt_ids, completion_ids], dim=1)  # (B, P+C)
        attention_mask = torch.cat([prompt_mask, completion_mask], dim=1)  # (B, P+C)

        logits_to_keep = completion_ids.size(1)  # we only need to compute the logits for the completion tokens
        
        max_left_pad = None
        batch_size = self.args.per_device_train_batch_size if mode == "train" else self.args.per_device_eval_batch_size
        try:
            # TRL 0.23.1 and below path
            if not has_images:
                # Left pad prompt before calculation old and ref hidden states
                left_pad_tokens_per_prompt = calculate_pad_tokens_in_prompt(prompt_completion_ids, logits_to_keep, self.processing_class.pad_token_id)
                max_left_pad = torch.max(left_pad_tokens_per_prompt).item()
        except:
            # TRL 0.24.0 and below path
            if images is None:
                # Left pad prompt before calculation old and ref hidden states
                left_pad_tokens_per_prompt = calculate_pad_tokens_in_prompt(prompt_completion_ids, logits_to_keep, self.processing_class.pad_token_id)
                max_left_pad = torch.max(left_pad_tokens_per_prompt).item()
        self.model.for_training()

        num_images = [len(img_list) for img_list in images] if images is not None else None

        # Get forward_kwargs for models with multimodal inputs
        if images is not None:
            prompts_text = [
                apply_chat_template(
                    {"prompt": prompt}, self.processing_class, tools=self.tools, **self.chat_template_kwargs
                )["prompt"]
                for prompt in prompts
            ]
            prompt_inputs = self.processing_class(images=images, text=prompts_text, padding=True, return_tensors="pt")
            prompt_inputs = super()._prepare_inputs(prompt_inputs)
            forward_kwargs = {k: v for k, v in prompt_inputs.items() if k not in ["input_ids", "attention_mask"]}
        else:
            forward_kwargs = {}

        # If token_type_ids are used, extend them with zeros for the completion part
        if "token_type_ids" in forward_kwargs:
            token_type_ids = forward_kwargs["token_type_ids"]
            forward_kwargs["token_type_ids"] = torch.cat(
                [token_type_ids, token_type_ids.new_zeros(completion_ids.shape)], dim=1
            )

        # When gradient checkpointing is enabled with use_reentrant=True (non default), calling the model inside a
        # torch.no_grad() block triggers a harmless PyTorch warning ("None of the inputs have requires_grad=True").
        # Temporarily disable checkpointing to avoid this warning during inference.
        with torch.no_grad(), disable_gradient_checkpointing(self.model, self.args.gradient_checkpointing_kwargs):
            # If the generation and optimization steps are misaligned—i.e., if generation does not occur at the end of
            # a full optimizer step (when gradient_accumulation_steps is not a multiple of generate_every)—then the
            # samples may come from an earlier version of the model. In that case, we need to track old_per_token_logps
            # for importance sampling. If the steps are aligned, importance sampling isn't necessary and we set
            # old_per_token_logps to None.
            # When using vLLM, we always compute old_per_token_logps for importance sampling, it was shown that the
            # distribution mismatch between vLLM and the training model can be large and harm the training.
            generate_every = self.args.steps_per_generation * self.num_iterations  # generation frequency
        
            if self.args.gradient_accumulation_steps % generate_every != 0 or (
                self.use_vllm
            ):
                old_per_token_logps, _ = self._get_per_token_logps_and_entropies(
                    self.model,
                    prompt_completion_ids,
                    attention_mask,
                    logits_to_keep,
                    batch_size,
                    num_images=num_images,
                    **forward_kwargs,  # may contain pixel_values, image_grid_thw, pixel_attention_mask and image_sizes
                )
            else:
                old_per_token_logps = None

            # Compute the importance sampling ratio when using vLLM, to correct for potential distribution mismatch
            if False and self.use_vllm and self.vllm_importance_sampling_correction:
                mask = completion_mask if not self.tools else completion_mask * tool_mask
                per_token_logps_diff = (old_per_token_logps - sampling_per_token_logps) * mask

                sequence_level_is = self.vllm_importance_sampling_mode in ["sequence_mask", "sequence_truncate"]
                if sequence_level_is:
                    per_sequence_logps_diff = per_token_logps_diff.sum(dim=-1, keepdim=True)
                    logps_diff = per_sequence_logps_diff
                else:
                    logps_diff = per_token_logps_diff

                vllm_importance_sampling_ratio = torch.exp(logps_diff)

                # vllm_importance_sampling_ratio.shape:
                #   token_* modes:     (B, T)  (per-token ratio)
                #   sequence_* modes:  (B, 1)  (per-sequence ratio)

                if self.vllm_importance_sampling_mode in ["sequence_truncate", "token_truncate"]:
                    vllm_importance_sampling_ratio = torch.clamp(
                        vllm_importance_sampling_ratio, max=self.vllm_importance_sampling_cap
                    )
                elif self.vllm_importance_sampling_mode in ["sequence_mask", "token_mask"]:
                    vllm_importance_sampling_ratio = vllm_importance_sampling_ratio.masked_fill(
                        vllm_importance_sampling_ratio > self.vllm_importance_sampling_cap, value=0.0
                    )
                else:
                    raise ValueError(
                        f"Unknown vLLM importance sampling level: {self.vllm_importance_sampling_mode}. Possible values are 'token_truncate', 'token_mask', 'sequence_truncate', and 'sequence_mask'."
                    )

            # Compute the per-token log probabilities for the reference model
            if self.beta != 0.0:
                if self.ref_model is not None:
                    ref_per_token_logps, _ = self._get_per_token_logps_and_entropies(
                        self.ref_model,
                        prompt_completion_ids,
                        attention_mask,
                        logits_to_keep,
                        batch_size=batch_size,
                        num_images=num_images,
                        **forward_kwargs,  # may contain pixel_values, image_grid_thw, pixel_attention_mask and image_sizes
                    )
                else:
                    # When training a PEFT adapter, how we obtain the reference depends on the setup:
                    # - New adapter: disabling adapters yields the base model.
                    # - Re-training an existing adapter: an initial copy is loaded under the name "ref".
                    model = self.accelerator.unwrap_model(self.model)
                    with use_adapter(model, adapter_name="ref" if "ref" in model.peft_config else None):
                        ref_per_token_logps, _ = self._get_per_token_logps_and_entropies(
                            self.model,
                            prompt_completion_ids,
                            attention_mask,
                            logits_to_keep,
                            batch_size=batch_size,
                            num_images=num_images,
                            **forward_kwargs,  # may contain pixel_values, image_grid_thw, pixel_attention_mask and image_sizes
                        )
            else:
                ref_per_token_logps = None

        # Decode
        prompts_text = self.processing_class.batch_decode(prompt_ids, skip_special_tokens=True)
        completions_text = self.processing_class.batch_decode(completion_ids, skip_special_tokens=True)

        # Merge extra_fields from rollout_func into inputs for reward functions
        if extra_fields:
            for i, inp in enumerate(inputs):
                for key, values in extra_fields.items():
                    if isinstance(values, list) and i < len(values):
                        inp[key] = values[i]
                    elif not isinstance(values, list):
                        inp[key] = values

        # Calculate rewards for each reward function. rewards_per_func aggregates rewards across all processes. This is
        # important because rewards will be normalized per group, and completions are distributed. We will later slice
        # rewards_per_func to extract each process's subset.
        rewards_per_func = self._calculate_rewards(inputs, prompts, completions, completion_ids_list)
        num_generations = self.num_generations if mode == "train" else self.num_generations_eval

        if self.multi_objective_aggregation == "sum_then_normalize":
            # Apply weights to each reward function's output and sum
            rewards = (rewards_per_func * self.reward_weights.to(device).unsqueeze(0)).nansum(dim=1)
            mean_grouped_rewards = rewards.view(-1, num_generations).mean(dim=1)
            mean_grouped_rewards = mean_grouped_rewards.repeat_interleave(num_generations, dim=0)
            if self.scale_rewards in ["group", "none"]:
                # If self.scale_rewards = "none", we'll only use std_rewards to check for zero std for logging
                if num_generations > 1:
                    std_rewards = rewards.view(-1, num_generations).std(dim=1)
                    std_rewards = std_rewards.repeat_interleave(num_generations, dim=0)
                else:  # doesn't occur during training, but could occur in eval when num_generations_eval=1
                    std_rewards = torch.zeros_like(rewards)
            elif self.scale_rewards == "batch":
                # Compute global std
                if rewards.numel() > 1:
                    std_rewards = rewards.std().expand_as(rewards)
                else:  # doesn't occur during training, but could occur in eval when num_generations_eval=batch_size=1
                    std_rewards = torch.zeros_like(rewards)
            else:
                raise ValueError(
                    f"Invalid value for scale_rewards: {self.scale_rewards}. Must be one of 'batch', 'group', or 'none'."
                )

            advantages = rewards - mean_grouped_rewards
            if self.scale_rewards != "none":
                advantages = advantages / (std_rewards + 1e-4)
            is_std_zero = torch.isclose(std_rewards, torch.zeros_like(std_rewards))  # for logging

        elif self.multi_objective_aggregation == "normalize_then_sum":
            grouped = rewards_per_func.view(-1, num_generations, len(self.reward_funcs))
            mean_k = torch.nanmean(grouped, dim=1, keepdim=True)
            std_k = nanstd(grouped, dim=1, keepdim=True) if num_generations > 1 else torch.zeros_like(mean_k)
            reward_k = (grouped - mean_k) / (std_k + 1e-4)
            reward_k = reward_k.view(-1, len(self.reward_funcs))
            rewards = (reward_k * self.reward_weights.to(device).unsqueeze(0)).nansum(dim=1)
            std_rewards = rewards.std().expand_as(rewards) if rewards.numel() > 1 else torch.zeros_like(rewards)
            advantages = (rewards - rewards.mean()) / (std_rewards + 1e-4)
            is_std_zero = torch.isclose(std_rewards, torch.zeros_like(std_rewards))  # for logging

        else:
            raise ValueError(
                f"Invalid multi_objective_aggregation: {self.multi_objective_aggregation}. Must be "
                "'sum_then_normalize' or 'normalize_then_sum'."
            )

        # Slice to keep only the local part of the data
        process_slice = slice(
            self.accelerator.process_index * len(prompts),
            (self.accelerator.process_index + 1) * len(prompts),
        )
        all_process_advantages = advantages.clone()  # keep the aggregated advantages for logging
        advantages = advantages[process_slice]

        # Calculate mean reward per function, but only for samples where the function was applied (non-NaN values)
        for i, reward_func_name in enumerate(self.reward_func_names):
            mean_rewards = torch.nanmean(rewards_per_func[:, i]).item()
            self._metrics[mode][f"rewards/{reward_func_name}/mean"].append(mean_rewards)
            std_func_rewards = nanstd(rewards_per_func[:, i]).item()
            self._metrics[mode][f"rewards/{reward_func_name}/std"].append(std_func_rewards)
        rewards = rewards_per_func.nansum(dim=1)
        self._metrics[mode]["reward"].append(rewards.mean().item())
        self._metrics[mode]["reward_std"].append(rewards.std().item())
        self._metrics[mode]["frac_reward_zero_std"].append(is_std_zero.float().mean().item())

        # Log prompt and completion texts
        self._logs["prompt"].extend(gather_object(prompts_text))
        self._logs["completion"].extend(gather_object(completions_text))
        for i, name in enumerate(self.reward_func_names):
            self._logs["rewards"][name].extend(rewards_per_func[:, i].tolist())
        self._logs["advantages"].extend(all_process_advantages.tolist())

        if images is not None:
            self._logs["images"].extend(gather_object(images))

        if False and self.use_vllm and self.vllm_importance_sampling_correction:
            delta = torch.abs(old_per_token_logps - sampling_per_token_logps)
            mask = completion_mask.bool() if not self.tools else (completion_mask * tool_mask).bool()
            delta = delta[mask]
            mean_delta = torch.mean(delta) if delta.numel() > 0 else torch.tensor(0.0, device=device)
            max_delta = torch.max(delta) if delta.numel() > 0 else torch.tensor(0.0, device=device)
            self._metrics[mode]["sampling/sampling_logp_difference/mean"].append(
                self.accelerator.gather(mean_delta).mean().item()
            )
            self._metrics[mode]["sampling/sampling_logp_difference/max"].append(
                self.accelerator.gather(max_delta).max().item()
            )

            if sequence_level_is:
                flat_is_ratio = vllm_importance_sampling_ratio.flatten()
            else:
                flat_is_ratio = vllm_importance_sampling_ratio[mask]

            min_importance_sampling_ratio = (
                torch.min(flat_is_ratio) if flat_is_ratio.numel() > 0 else torch.tensor(0.0, device=device)
            )
            mean_importance_sampling_ratio = (
                torch.mean(flat_is_ratio) if flat_is_ratio.numel() > 0 else torch.tensor(0.0, device=device)
            )
            max_importance_sampling_ratio = (
                torch.max(flat_is_ratio) if flat_is_ratio.numel() > 0 else torch.tensor(0.0, device=device)
            )
            self._metrics[mode]["sampling/importance_sampling_ratio/min"].append(
                nanmin(self.accelerator.gather(min_importance_sampling_ratio)).item()
            )
            self._metrics[mode]["sampling/importance_sampling_ratio/mean"].append(
                self.accelerator.gather(mean_importance_sampling_ratio).nanmean().item()
            )
            self._metrics[mode]["sampling/importance_sampling_ratio/max"].append(
                nanmax(self.accelerator.gather(max_importance_sampling_ratio)).item()
            )

        output = {
            "prompt_ids": prompt_ids,
            "prompt_mask": prompt_mask,
            "completion_ids": completion_ids,
            "completion_mask": completion_mask,
            "advantages": advantages,
            "num_items_in_batch": num_items_in_batch,
        }
        if old_per_token_logps is not None:
            output["old_per_token_logps"] = old_per_token_logps
        if False and self.use_vllm and self.vllm_importance_sampling_correction:
            output["importance_sampling_ratio"] = vllm_importance_sampling_ratio
        if sampling_per_token_logps is not None:
            output["sampling_per_token_logps"] = sampling_per_token_logps
        if ref_per_token_logps is not None:
            output["ref_per_token_logps"] = ref_per_token_logps
        if "pixel_values" in forward_kwargs:
            output["pixel_values"] = forward_kwargs["pixel_values"]
        if "image_grid_thw" in forward_kwargs:
            output["image_grid_thw"] = forward_kwargs["image_grid_thw"]
        if "pixel_attention_mask" in forward_kwargs:
            output["pixel_attention_mask"] = forward_kwargs["pixel_attention_mask"]
        if "image_sizes" in forward_kwargs:
            output["image_sizes"] = forward_kwargs["image_sizes"]
        if "token_type_ids" in forward_kwargs:
            output["token_type_ids"] = forward_kwargs["token_type_ids"]
        if images is not None:
            output["num_images"] = num_images
        if max_left_pad is not None:
            output["max_left_pad"] = torch.tensor(prompt_ids.shape[0] * [max_left_pad]).unsqueeze(-1)        
        try:
            if self.use_vllm and getattr(self, "vllm_importance_sampling_correction", False):
                output["sampling_per_token_logps"] = sampling_per_token_logps
        except NameError:
            output["sampling_per_token_logps"] = None
        if self.tools:
            output["tool_mask"] = tool_mask
        return output

    def compute_liger_loss(self, unwrapped_model, inputs):
        # Compute the per-token log probabilities for the model
        prompt_ids, prompt_mask = inputs["prompt_ids"], inputs["prompt_mask"]
        completion_ids, completion_mask = inputs["completion_ids"], inputs["completion_mask"]
        input_ids = torch.cat([prompt_ids, completion_ids], dim=1)
        attention_mask = torch.cat([prompt_mask, completion_mask], dim=1)
        logits_to_keep = completion_ids.size(1)  # we only need to compute the logits for the completion tokens

        # Get the last hidden state of the model
        last_hidden_state = self._get_last_hidden_state(
            unwrapped_model,
            input_ids,
            attention_mask,
            logits_to_keep,
            inputs.get("pixel_values"),
            inputs.get("image_grid_thw"),
            inputs.get("pixel_attention_mask"),
            inputs.get("image_sizes"),
        )

        # compute loss and metrics using liger grpo loss
        loss, metrics = self.liger_grpo_loss(
            _input=last_hidden_state,
            lin_weight=unwrapped_model.lm_head.weight,
            selected_token_ids=completion_ids,
            attention_mask=completion_mask,
            advantages=inputs["advantages"],
            bias=unwrapped_model.lm_head.bias,
            old_per_token_logps=inputs.get("old_per_token_logps"),
            ref_per_token_logps=inputs.get("ref_per_token_logps"),
        )
        # Extract metrics from the liger_grpo_loss output
        # KL divergence is the first metric when beta is non-zero
        mean_kl = metrics[0] if self.beta != 0.0 else None
        clip_ratio = metrics[-1]

        mode = "train" if self.model.training else "eval"
        if self.beta != 0.0:
            self._metrics[mode]["kl"].append(self.accelerator.gather(mean_kl).mean().item())
        self._metrics[mode]["clip_ratio"].append(self.accelerator.gather(clip_ratio).mean().item())
        normalizer = self.current_gradient_accumulation_steps if mode == "train" else 1.0  # no accum in eval
        return loss / normalizer

    def compute_loss(
        self, model, inputs, return_outputs = False, num_items_in_batch = None
    ):
        if return_outputs:
            raise ValueError("The GRPOTrainer does not support returning outputs")
        # Compute the per-token log probabilities for the model

        prompt_ids, prompt_mask = inputs["prompt_ids"], inputs["prompt_mask"]
        completion_ids, completion_mask = (
            inputs["completion_ids"],
            inputs["completion_mask"],
        )
        pixel_values, image_grid_thw = (
            inputs.get("pixel_values", None),
            inputs.get("image_grid_thw", None),
        )
        pixel_attention_mask, image_sizes = (
            inputs.get("pixel_attention_mask", None),
            inputs.get("image_sizes", None),
        )
        num_items_in_batch = inputs.get("num_items_in_batch", None)
        sampling_per_token_logps = inputs.get("sampling_per_token_logps", None)
        current_gradient_accumulation_steps = self.current_gradient_accumulation_steps
        num_processes = self.accelerator.num_processes

        input_ids = torch.cat([prompt_ids, completion_ids], dim = 1)
        bsz, qlen = input_ids.shape
        attention_mask = torch.cat([prompt_mask, completion_mask], dim = 1)
        # attention_mask = None
        logits_to_keep = completion_ids.size(
            1
        )  # we only need to compute the logits for the completion tokens
        _input_ids = input_ids
        _logits_to_keep = logits_to_keep

        get_logps_func = (
            lambda model,
            input_ids,
            attention_mask,
            logits_to_keep,
            batch_size = None,
            compute_entropy = False,
            compute_efficient = False: self._get_per_token_logps(
                model, input_ids, attention_mask, logits_to_keep, compute_efficient
            )
            if hasattr(self, "_get_per_token_logps")
            else self._get_per_token_logps_and_entropies(
                model,
                input_ids,
                attention_mask,
                logits_to_keep,
                batch_size,
                compute_entropy,
                compute_efficient,
            )[0]
        )  # logps

        per_token_logps = get_logps_func(
            model, input_ids, attention_mask, logits_to_keep, compute_efficient = True
        )
        # Compute the KL divergence between the model and the reference model
        # _prepare_inputs doesn't return reference log probs anymore. We need to calculate it ourselves.
        # https://github.com/huggingface/trl/blob/05bc43e960396581e458195b8388efe6b82cae1f/trl/trainer/grpo_trainer.py#L1328
        # if self.beta != 0.0:
        #     with torch.inference_mode(), model.disable_adapter():
        #         ref_per_token_logps = per_token_logps = get_logps_func(model, input_ids, attention_mask, logits_to_keep)
        # else:
        #     ref_per_token_logps = None
        ref_logps = inputs.get("ref_per_token_logps", None)
        # per_token_kl = torch.exp(ref_per_token_logps - per_token_logps) - (ref_per_token_logps - per_token_logps) - 1
        # x - x.detach() allows for preserving gradients from x
        advantages = inputs["advantages"]
        # per_token_loss = torch.exp(per_token_logps - per_token_logps.detach()) * advantages.unsqueeze(1)
        # per_token_loss = -(per_token_loss - self.beta * per_token_kl)
        # loss = ((per_token_loss * completion_mask).sum(dim=1) / completion_mask.sum(dim=1)).mean()
        old_logps = inputs.get("old_per_token_logps", None)

        input_ids = input_ids[:, -logits_to_keep:]

        # Get logit softcapping and logit scale
        logit_softcapping = getattr(model.config, "final_logit_softcapping", 0)  # Gemma
        if logit_softcapping is None:
            logit_softcapping = 0
        logit_scale_multiply = getattr(model.config, "logit_scale", 0)  # Cohere
        if logit_scale_multiply is None:
            logit_scale_multiply = 0
        logit_scale_divide = getattr(model.config, "logits_scaling", 0)  # Granite
        if logit_scale_divide is None:
            logit_scale_divide = 0

        max_left_pad = inputs.get("max_left_pad", 0)
        if per_token_logps is not None:
            loss, completion_length, mean_kl, delta, flat_is_ratio = (
                grpo_compute_loss_slow(
                    ref_logps,
                    per_token_logps,
                    old_logps,
                    input_ids,
                    completion_mask,
                    self.beta,
                    advantages,
                    pixel_values = pixel_values,
                    image_grid_thw = image_grid_thw,
                    loss_type = self.args.loss_type,
                    importance_sampling_level = self.importance_sampling_level,
                    epsilon_low = self.epsilon_low,
                    epsilon_high = self.epsilon_high,
                    max_completion_length = self.args.max_completion_length,
                    delta = self.args.delta,
                    temperature = self.args.temperature,
                    max_left_pad = max_left_pad,
                    logit_softcapping = logit_softcapping,
                    logit_scale_multiply = logit_scale_multiply,
                    logit_scale_divide = logit_scale_divide,
                    num_items_in_batch = num_items_in_batch,
                    current_gradient_accumulation_steps = current_gradient_accumulation_steps,
                    num_processes = num_processes,
                    sampling_per_token_logps = sampling_per_token_logps,
                )
            )
        else:
            if hasattr(self.args, "loss_type"):
                loss, completion_length, mean_kl, delta, flat_is_ratio = (
                    grpo_accumulated_loss(
                        trainer = self,
                        input_ids = _input_ids,
                        pixel_values = pixel_values,
                        image_grid_thw = image_grid_thw,
                        logits_to_keep = logits_to_keep,
                        completion_mask = completion_mask,
                        advantages = advantages,
                        old_logps = old_logps,
                        ref_logps = ref_logps,
                        n_chunks = self.args.unsloth_num_chunks,
                        loss_type = self.args.loss_type,
                        importance_sampling_level = self.importance_sampling_level,
                        epsilon_low = self.epsilon_low,
                        epsilon_high = self.epsilon_high,
                        max_completion_length = self.args.max_completion_length,
                        delta = self.args.delta,
                        temperature = self.args.temperature,
                        max_left_pad = max_left_pad,
                        logit_softcapping = logit_softcapping,
                        logit_scale_multiply = logit_scale_multiply,
                        logit_scale_divide = logit_scale_divide,
                        attention_mask = attention_mask,
                        num_items_in_batch = num_items_in_batch,
                        current_gradient_accumulation_steps = current_gradient_accumulation_steps,
                        num_processes = num_processes,
                        sampling_per_token_logps = sampling_per_token_logps,
                    )
                )
            else:
                # to ensure backwards compatibility with trl 0.15.2 and maybe even 0.17
                loss, completion_length, mean_kl = grpo_accumulated_loss(
                    trainer = self,
                    input_ids = _input_ids,
                    logits_to_keep = logits_to_keep,
                    completion_mask = completion_mask,
                    advantages = advantages,
                    old_logps = old_logps,
                    ref_logps = ref_logps,
                    n_chunks = self.args.unsloth_num_chunks,
                    temperature = self.args.temperature,
                    logit_softcapping = logit_softcapping,
                    logit_scale_multiply = logit_scale_multiply,
                    logit_scale_divide = logit_scale_divide,
                    attention_mask = attention_mask,
                )

        if "train" in self._metrics:
            mode = "eval" if self.control.should_evaluate else "train"
            self._metrics[mode]["completion_length"].append(completion_length.item())
            self._metrics[mode]["kl"].append(mean_kl.item())
        else:
            self._metrics["completion_length"].append(completion_length.item())
            self._metrics["kl"].append(mean_kl.item())

        if (
            self.use_vllm
            and delta is not None
            and getattr(self, "vllm_importance_sampling_correction", False)
        ):
            mean_delta = (
                torch.mean(delta)
                if delta.numel() > 0
                else torch.tensor(0.0, device = self.model.device)
            )
            max_delta = (
                torch.max(delta)
                if delta.numel() > 0
                else torch.tensor(0.0, device = self.model.device)
            )
            self._metrics[mode]["sampling/sampling_logp_difference/mean"].append(
                self.accelerator.gather(mean_delta).mean().item()
            )
            self._metrics[mode]["sampling/sampling_logp_difference/max"].append(
                self.accelerator.gather(max_delta).max().item()
            )

            min_importance_sampling_ratio = (
                torch.min(flat_is_ratio)
                if flat_is_ratio.numel() > 0
                else torch.tensor(0.0, device = self.model.device)
            )
            mean_importance_sampling_ratio = (
                torch.mean(flat_is_ratio)
                if flat_is_ratio.numel() > 0
                else torch.tensor(0.0, device = self.model.device)
            )
            max_importance_sampling_ratio = (
                torch.max(flat_is_ratio)
                if flat_is_ratio.numel() > 0
                else torch.tensor(0.0, device = self.model.device)
            )
            self._metrics[mode]["sampling/importance_sampling_ratio/min"].append(
                self.accelerator.gather(min_importance_sampling_ratio)
                .nan_to_num(nan = float("inf"))
                .min()
                .item()
            )
            self._metrics[mode]["sampling/importance_sampling_ratio/mean"].append(
                self.accelerator.gather(mean_importance_sampling_ratio).nanmean().item()
            )
            self._metrics[mode]["sampling/importance_sampling_ratio/max"].append(
                self.accelerator.gather(max_importance_sampling_ratio)
                .nan_to_num(nan = float("-inf"))
                .max()
                .item()
            )

        return loss

    @staticmethod
    def get_sapo_token_loss(unclipped_token_loss: torch.Tensor, temperature: float) -> torch.Tensor:
        sigmoid_input = temperature * (unclipped_token_loss - 1)
        sigmoid_smoothed_loss = torch.nn.functional.sigmoid(sigmoid_input)
        sapo_token_loss = sigmoid_smoothed_loss * 4 / temperature
        return sapo_token_loss

    @staticmethod
    def get_off_policy_mask(
        advantages: torch.Tensor,
        per_token_logps: torch.Tensor,
        sampling_per_token_logps: torch.Tensor,
        mask: torch.Tensor,
        off_policy_threshold: float,
    ) -> torch.Tensor:
        """
        Computes the Off-Policy Sequence Mask from DeepSeek-V3.2 paper. Returns a (B, 1) tensor where 1.0 indicates
        "Keep" and 0.0 indicates "Drop".
        """
        # forward KL div: log(pi_old) - log(pi_theta)
        kl_div = sampling_per_token_logps - per_token_logps.detach()
        # Sequence-level Mean KL (ignoring prompt+padding)
        seq_kl_sum = (kl_div * mask).sum(dim=1, keepdim=True)
        avg_seq_kl = seq_kl_sum / mask.sum(dim=1, keepdim=True).clamp(min=1.0)
        # Keep if (Advantage >= 0) OR (KL <= delta)
        is_pos_adv = advantages >= 0
        is_low_kl = avg_seq_kl <= off_policy_threshold
        return (is_pos_adv | is_low_kl).to(dtype=mask.dtype)  # (B, 1)

    def _compute_loss(self, model, inputs):
        # Compute the per-token log probabilities for the model
        prompt_ids, prompt_mask = inputs["prompt_ids"], inputs["prompt_mask"]
        completion_ids, completion_mask = inputs["completion_ids"], inputs["completion_mask"]
        input_ids = torch.cat([prompt_ids, completion_ids], dim=1)
        attention_mask = torch.cat([prompt_mask, completion_mask], dim=1)
        logits_to_keep = completion_ids.size(1)  # we only need to compute the logits for the completion tokens
        mask = completion_mask if not self.tools else completion_mask * inputs["tool_mask"]

        # Compute the per_token_logps and the entropy at each position in the completion
        per_token_logps, entropies = self._get_per_token_logps_and_entropies(
            model,
            input_ids,
            attention_mask,
            logits_to_keep,
            compute_entropy=True,
            pixel_values=inputs.get("pixel_values"),
            image_grid_thw=inputs.get("image_grid_thw"),
            num_images=inputs.get("num_images"),
            pixel_attention_mask=inputs.get("pixel_attention_mask"),
            image_sizes=inputs.get("image_sizes"),
            token_type_ids=inputs.get("token_type_ids"),
        )

        if self.top_entropy_quantile < 1.0:
            entropy_mask = self.get_high_entropy_mask(entropies, mask, 1 - self.top_entropy_quantile)
        else:
            entropy_mask = None

        # Compute the loss
        advantages = inputs["advantages"]
        # In the base GRPO implementation, advantages are expected to have shape (B,). To support subclasses that
        # provide advantages with shape (B, T) (e.g., MiniLLM), we *conditionally* unsqueeze the tensor.
        if advantages.dim() == 1:
            advantages = advantages.unsqueeze(1)
        # When num_iterations == 1 and steps_per_generation <= gradient_accumulation_steps,
        # old_per_token_logps == per_token_logps. In this case we can skip its computation
        # (see _generate_and_score_completions) and instead use per_token_logps.detach().
        # The exception is when using vLLM, where we always compute old_per_token_logps
        # for importance sampling
        old_per_token_logps = inputs.get("old_per_token_logps")
        old_per_token_logps = per_token_logps.detach() if old_per_token_logps is None else old_per_token_logps

        if self.off_policy_mask_threshold is not None:
            # OPSM should use inference-time logprobs to detect both sources of off-policyness:
            # 1. Drift from gradient updates (always present)
            # 2. Drift from training-inference mismatch (when using vLLM)
            # When using vLLM, prioritize sampling_per_token_logps, otherwise use old_per_token_logps
            sampling_per_token_logps = inputs.get("sampling_per_token_logps", old_per_token_logps)

            off_policy_mask = self.get_off_policy_mask(
                advantages=advantages,
                per_token_logps=per_token_logps,
                sampling_per_token_logps=sampling_per_token_logps,
                mask=mask,
                off_policy_threshold=self.off_policy_mask_threshold,
            )

        log_ratio = per_token_logps - old_per_token_logps
        if self.importance_sampling_level == "token":
            log_importance_weights = log_ratio
        elif self.importance_sampling_level == "sequence":
            log_importance_weights = (log_ratio * mask).sum(-1) / mask.sum(-1).clamp(min=1.0)
            log_importance_weights = log_importance_weights.unsqueeze(-1)
        else:
            raise ValueError(
                f"Unknown importance sampling level: {self.importance_sampling_level}. Possible values are 'token' "
                "and 'sequence'."
            )

        coef_1 = torch.exp(log_importance_weights)

        # Compute the KL divergence between the model and the reference model
        if self.beta != 0.0:
            ref_per_token_logps = inputs["ref_per_token_logps"]
            per_token_kl = (
                torch.exp(ref_per_token_logps - per_token_logps) - (ref_per_token_logps - per_token_logps) - 1
            )
            # Importance sampling correction for the KL divergence
            if self.args.use_bias_correction_kl:
                per_token_kl = per_token_kl * coef_1

        # From here, log_importance_weights (and all subsequent tensors, coef_1, coef_2, etc.) shape depends on
        # importance_sampling_level: "token" level: (B, T); "sequence" level: (B, 1)
        if self.loss_type == "cispo":
            clamped_ratios = torch.clamp(coef_1, max=self.epsilon_high).detach()
            per_token_loss = -clamped_ratios * advantages * per_token_logps
        elif self.loss_type in ["grpo", "bnpo", "dr_grpo", "dapo"]:
            coef_2 = torch.clamp(coef_1, 1 - self.epsilon_low, 1 + self.epsilon_high)
            # Two-sided clipping
            if self.args.delta is not None:
                coef_1 = torch.clamp(coef_1, max=self.args.delta)

            per_token_loss1 = coef_1 * advantages
            per_token_loss2 = coef_2 * advantages
            per_token_loss = -torch.min(per_token_loss1, per_token_loss2)
        elif self.loss_type == "sapo":
            per_token_loss = torch.empty_like(coef_1)
            positive_advantages_mask = advantages.repeat([1, coef_1.shape[1]]) > 0
            per_token_loss[positive_advantages_mask] = self.get_sapo_token_loss(
                coef_1[positive_advantages_mask], self.args.sapo_temperature_pos
            )
            per_token_loss[~positive_advantages_mask] = self.get_sapo_token_loss(
                coef_1[~positive_advantages_mask], self.args.sapo_temperature_neg
            )
            per_token_loss = -per_token_loss * advantages
        else:
            raise ValueError(f"Unknown loss type: {self.loss_type}")

        if self.off_policy_mask_threshold is not None:
            per_token_loss = per_token_loss * off_policy_mask

        if entropy_mask is not None:
            per_token_loss = per_token_loss * entropy_mask

        if self.use_vllm and self.vllm_importance_sampling_correction:
            per_token_loss = per_token_loss * inputs["importance_sampling_ratio"]

        if self.beta != 0.0:
            per_token_loss = per_token_loss + self.beta * per_token_kl

        mode = "train" if self.model.training else "eval"
        if self.loss_type in ["grpo", "sapo"]:
            loss = ((per_token_loss * mask).sum(-1) / mask.sum(-1).clamp(min=1.0)).mean()
            normalizer = self.current_gradient_accumulation_steps if mode == "train" else 1.0  # no accum in eval
            loss = loss / normalizer
        elif self.loss_type == "bnpo":
            loss = (per_token_loss * mask).sum() / mask.sum().clamp(min=1.0)
            normalizer = self.current_gradient_accumulation_steps if mode == "train" else 1.0  # no accum in eval
            loss = loss / normalizer
        elif self.loss_type == "dr_grpo":
            loss = (per_token_loss * mask).sum() / (per_token_loss.size(0) * self.max_completion_length)
            normalizer = self.current_gradient_accumulation_steps if mode == "train" else 1.0  # no accum in eval
            loss = loss / normalizer
        elif self.loss_type in ["cispo", "dapo"]:
            normalizer = inputs["num_items_in_batch"] / self.accelerator.num_processes
            loss = (per_token_loss * mask).sum() / normalizer
        else:
            raise ValueError(f"Unknown loss type: {self.loss_type}")

        # Log the metrics
        completion_token_count = mask.sum().clamp(min=1.0)

        def masked_batch_mean(x):
            if x.shape[1] == 1:  # when importance_sampling_level == "sequence"
                return x.mean()
            else:
                return (x * mask).sum() / completion_token_count

        if self.beta != 0.0:
            mean_kl = masked_batch_mean(per_token_kl)
            self._metrics[mode]["kl"].append(self.accelerator.gather(mean_kl).nanmean().item())

        mean_entropy = masked_batch_mean(entropies)
        self._metrics[mode]["entropy"].append(self.accelerator.gather(mean_entropy).nanmean().item())

        if self.loss_type in ["grpo", "bnpo", "dr_grpo", "dapo"]:
            # Compute the clipped probability ratios
            is_low_clipped = (coef_1 < 1 - self.epsilon_low) & (advantages < 0)
            is_high_clipped = (coef_1 > 1 + self.epsilon_high) & (advantages > 0)
            is_region_clipped = is_low_clipped | is_high_clipped

            low_clip = masked_batch_mean(is_low_clipped.float())
            high_clip = masked_batch_mean(is_high_clipped.float())
            clip_ratio = masked_batch_mean(is_region_clipped.float())

            gathered_low_clip = self.accelerator.gather(low_clip)
            self._metrics[mode]["clip_ratio/low_mean"].append(gathered_low_clip.nanmean().item())
            self._metrics[mode]["clip_ratio/low_min"].append(nanmin(gathered_low_clip).item())
            gathered_high_clip = self.accelerator.gather(high_clip)
            self._metrics[mode]["clip_ratio/high_mean"].append(gathered_high_clip.nanmean().item())
            self._metrics[mode]["clip_ratio/high_max"].append(nanmax(gathered_high_clip).item())
            gathered_clip_ratio = self.accelerator.gather(clip_ratio)
            self._metrics[mode]["clip_ratio/region_mean"].append(gathered_clip_ratio.nanmean().item())
        elif self.loss_type == "cispo":
            is_cispo_clipped = (coef_1 > self.epsilon_high) & (advantages > 0)
            cispo_clip_ratio = masked_batch_mean(is_cispo_clipped.float())
            gathered_cispo_clip_ratio = self.accelerator.gather(cispo_clip_ratio)
            self._metrics[mode]["cispo_clip_ratio"].append(gathered_cispo_clip_ratio.nanmean().item())

        return loss

    def prediction_step(self, model, inputs, prediction_loss_only, ignore_keys: list[str] | None = None):
        inputs = self._prepare_inputs(inputs)
        with torch.no_grad():
            with self.compute_loss_context_manager():
                loss = self.compute_loss(model, inputs)
            loss = loss.mean().detach()
        return loss, None, None

    def log(self, logs: dict[str, float], start_time: float | None = None) -> None:
        mode = "train" if self.model.training else "eval"
        metrics = {key: sum(val) / len(val) for key, val in self._metrics[mode].items()}  # average the metrics

        # This method can be called both in training and evaluation. When called in evaluation, the keys in `logs`
        # start with "eval_". We need to add the prefix "eval_" to the keys in `metrics` to match the format.
        if mode == "eval":
            metrics = {f"eval_{key}": val for key, val in metrics.items()}

        logs = {**logs, **metrics}
        super().log(logs, start_time)
        self._metrics[mode].clear()

        if self.accelerator.is_main_process and self.log_completions:
            if is_rich_available():
                print_prompt_completions_sample(
                    self._logs["prompt"],
                    self._logs["completion"],
                    self._logs["rewards"],
                    self._logs["advantages"],
                    self.state.global_step,
                    self.num_completions_to_print,
                )

            logging_backends = []
            if self.args.report_to and "wandb" in self.args.report_to and wandb.run is not None:
                logging_backends.append(wandb)
            if self.args.report_to and "trackio" in self.args.report_to:
                logging_backends.append(trackio)

            table = {
                "step": [str(self.state.global_step)] * len(self._logs["prompt"]),
                "prompt": self._logs["prompt"],
                "completion": self._logs["completion"],
                **self._logs["rewards"],
                "advantage": self._logs["advantages"],
            }

            df_base = pd.DataFrame(table)
            images_raw = self._logs["images"] or []

            for logging_backend in logging_backends:
                if images_raw:
                    images = []
                    for image_list in self._logs["images"]:
                        images.append([logging_backend.Image(image) for image in image_list])
                    df = pd.concat(
                        [df_base, pd.Series(images, name="image")],
                        axis=1,
                        copy=False,
                    )
                else:
                    df = df_base

                if self.log_unique_prompts:
                    df = df.drop_duplicates(subset=["prompt"])

                logging_backend.log({"completions": logging_backend.Table(dataframe=df)})

    # Ensure the model card is saved along with the checkpoint
    def _save_checkpoint(self, model, trial):
        if self.args.hub_model_id is None:
            model_name = Path(self.args.output_dir).name
        else:
            model_name = self.args.hub_model_id.split("/")[-1]
        self.create_model_card(model_name=model_name)
        super()._save_checkpoint(model, trial)
class UnslothGRPOTrainer(_UnslothGRPOTrainer):
    """
    
Trainer for the Group Relative Policy Optimization (GRPO) method. This algorithm was initially proposed in the
paper [DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language
Models](https://huggingface.co/papers/2402.03300).

Example:

```python
from trl import GRPOTrainer
from trl.rewards import accuracy_reward
from datasets import load_dataset

dataset = load_dataset("trl-lib/DeepMath-103K", split="train")

trainer = GRPOTrainer(
    model="Qwen/Qwen2.5-0.5B-Instruct",
    reward_funcs=accuracy_reward,
    train_dataset=dataset,
)
trainer.train()
```

Args:
    model (`str` or [`~transformers.PreTrainedModel`] or [`~peft.PeftModel`]):
        Model to be trained. Can be either:

        - A string, being the *model id* of a pretrained model hosted inside a model repo on huggingface.co, or a
          path to a *directory* containing model weights saved using
          [`~transformers.PreTrainedModel.save_pretrained`], e.g., `'./my_model_directory/'`. The model is loaded
          using `<ModelArchitecture>.from_pretrained` (where `<ModelArchitecture>` is derived from the model
          config) with the keyword arguments in `args.model_init_kwargs`.
        - A [`~transformers.PreTrainedModel`] object. Only causal language models are supported.
        - A [`~peft.PeftModel`] object. Only causal language models are supported.
    reward_funcs (`RewardFunc | list[RewardFunc]`):
        Reward functions to be used for computing the rewards. To compute the rewards, we call all the reward
        functions with the prompts and completions and sum the rewards. Can be either:

        - A single reward function, such as:
            - A string: The *model ID* of a pretrained model hosted inside a model repo on huggingface.co, or a
            path to a *directory* containing model weights saved using
            [`~transformers.PreTrainedModel.save_pretrained`], e.g., `'./my_model_directory/'`. The model is loaded
            using [`~transformers.AutoModelForSequenceClassification.from_pretrained`] with `num_labels=1` and the
            keyword arguments in `args.model_init_kwargs`.
            - A [`~transformers.PreTrainedModel`] object: Only sequence classification models are supported.
            - A custom reward function: The function is provided with the prompts and the generated completions,
              plus any additional columns in the dataset. It should return a list of rewards. Custom reward
               functions can be either synchronous or asynchronous and can also return `None` when the reward is
               not applicable to those samples. This is useful for multi-task training where different reward
               functions apply to different types of samples. When a reward function returns `None` for a sample,
               that reward function is excluded from the reward calculation for that sample. For more details, see
               [Using a custom reward
              function](#using-a-custom-reward-function).

              The trainer's state is also passed to the reward function. The trainer's state is an instance of
              [`~transformers.TrainerState`] and can be accessed by accessing the `trainer_state` argument to the
              reward function's signature.
        - A list of reward functions, where each item can independently be any of the above types. Mixing different
        types within the list (e.g., a string model ID and a custom reward function) is allowed.
    args ([`GRPOConfig`], *optional*):
        Configuration for this trainer. If `None`, a default configuration is used.
    train_dataset ([`~datasets.Dataset`] or [`~datasets.IterableDataset`]):
        Dataset to use for training. It must include a column `"prompt"`. Any additional columns in the dataset is
        ignored. The format of the samples can be either:

        - [Standard](dataset_formats#standard): Each sample contains plain text.
        - [Conversational](dataset_formats#conversational): Each sample contains structured messages (e.g., role
          and content).
    eval_dataset ([`~datasets.Dataset`], [`~datasets.IterableDataset`] or `dict[str, Dataset | IterableDataset]`):
        Dataset to use for evaluation. It must meet the same requirements as `train_dataset`.
    processing_class ([`~transformers.PreTrainedTokenizerBase`], [`~transformers.ProcessorMixin`], *optional*):
        Processing class used to process the data. The padding side must be set to "left". If `None`, the
        processing class is loaded from the model's name with [`~transformers.AutoProcessor.from_pretrained`]. A
        padding token, `tokenizer.pad_token`, must be set. If the processing class has not set a padding token,
        `tokenizer.eos_token` will be used as the default.
    reward_processing_classes ([`~transformers.PreTrainedTokenizerBase`] or `list[PreTrainedTokenizerBase]`, *optional*):
        Processing classes corresponding to the reward functions specified in `reward_funcs`. Can be either:

        - A single processing class: Used when `reward_funcs` contains only one reward function.
        - A list of processing classes: Must match the order and length of the reward functions in `reward_funcs`.
        If set to `None`, or if an element of the list corresponding to a [`~transformers.PreTrainedModel`] is
        `None`, the tokenizer for the model is automatically loaded using
        [`~transformers.AutoTokenizer.from_pretrained`]. For elements in `reward_funcs` that are custom reward
        functions (not [`~transformers.PreTrainedModel`]), the corresponding entries in `reward_processing_classes`
        are ignored.
    callbacks (list of [`~transformers.TrainerCallback`], *optional*):
        List of callbacks to customize the training loop. Will add those to the list of default callbacks detailed
        in [here](https://huggingface.co/docs/transformers/main_classes/callback).

        If you want to remove one of the default callbacks used, use the [`~transformers.Trainer.remove_callback`]
        method.
    optimizers (`tuple[torch.optim.Optimizer | None, torch.optim.lr_scheduler.LambdaLR | None]`, *optional*, defaults to `(None, None)`):
        A tuple containing the optimizer and the scheduler to use. Will default to an instance of `AdamW` on your
        model and a scheduler given by [`~transformers.get_linear_schedule_with_warmup`] controlled by `args`.
    peft_config ([`~peft.PeftConfig`], *optional*):
        PEFT configuration used to wrap the model. If `None`, the model is not wrapped.
    tools (list of `Callable`, *optional*):
        A list of callable tool functions that the model can invoke during generation. Each tool should be a
        standard Python function with properly type-hinted arguments and return values, and a Google-style
        docstring describing its purpose, arguments, and return value. For more details, see:
        https://huggingface.co/docs/transformers/en/chat_extras#passing-tools. The model uses the function's name,
        type hints, and docstring to determine how to call it. Ensure that the model's chat template supports tool
        use and that it has been fine-tuned for tool calling.
    rollout_func (`RolloutFunc`, *optional*):
        Function to use for generating completions. It receives the list of prompts allocated to the current
        process and the trainer instance. It must return a dict with `"prompt_ids"`, `"completion_ids"`, and
        `"logprobs"` fields. Any other fields are forwarded to the reward functions. This feature is experimental
        and may change or be removed at any time without prior notice.

    """
    def __init__(
        self,
        model,
        reward_funcs,
        args = None,
        train_dataset = None,
        eval_dataset = None,
        processing_class = None,
        reward_processing_classes = None,
        callbacks = None,
        peft_config = None,
        tools = None,
        rollout_func = None,
        **kwargs
    ):
        if args is None: args = UnslothGRPOConfig()
        use_bf16 = getattr(args, 'bf16', False)
        if type(use_bf16) is not bool: use_bf16 = False
        use_fp16 = getattr(args, 'fp16', False)
        if type(use_fp16) is not bool: use_fp16 = False
        force_float32 = False
        full_finetuning = os.environ.get('UNSLOTH_ENABLE_FULL_FINETUNING', '0') == '1'
        if not full_finetuning and (os.environ.get('UNSLOTH_FORCE_FLOAT32', '0') == '1'):
            print('Unsloth: Switching to float32 training since model cannot work with float16')
            force_float32 = True
        mixed_precision_dtype = os.environ.get('UNSLOTH_MIXED_PRECISION', 'float32')
        dtype = getattr(model.config, 'dtype', None) or getattr(model.config, 'torch_dtype', None)
        if dtype is None: dtype = model.get_input_embeddings().weight.dtype
        from unsloth_zoo.utils import _get_dtype
        dtype = _get_dtype(dtype)
        float16 = dtype == torch.float16
        if not force_float32 and (float16 and use_bf16): raise TypeError('Unsloth: Model is in float16 precision but you want to use bfloat16 precision. Set fp16 to `True` and bf16 to `False`')
        if not force_float32 and (not float16 and use_fp16): raise TypeError('Unsloth: Model is in bfloat16 precision but you want to use float16 precision. Set fp16 to `False` and bf16 to `True`')
        if force_float32:
            # Forced float32 training
            args.fp16 = False
            args.bf16 = False
            os.environ['ACCELERATE_MIXED_PRECISION'] = 'no'
            if hasattr(args, 'mixed_precision'): args.mixed_precision = 'no'
            # args.mixed_precision is a new argument which needs to be set now
        elif (not use_bf16 and not use_fp16) and mixed_precision_dtype == 'float32':
            # Mixed precision training
            args.fp16 = float16
            args.bf16 = not float16
            os.environ['ACCELERATE_MIXED_PRECISION'] = 'fp16' if float16 else 'bf16'
            if hasattr(args, 'mixed_precision'): args.mixed_precision = 'fp16' if float16 else 'bf16'
            # args.mixed_precision is a new argument which needs to be set now
        elif mixed_precision_dtype == 'bfloat16':
            # Both False since bfloat16 full finetuning doesn't do any autocasting.
            args.fp16 = False
            args.bf16 = False
            os.environ['ACCELERATE_MIXED_PRECISION'] = 'no'
            if hasattr(args, 'mixed_precision'): args.mixed_precision = 'no'
            # args.mixed_precision is a new argument which needs to be set now
        
        if getattr(args, 'eval_dataset', None) is not None and getattr(args, 'eval_strategy', 'no') == 'no':
            args.eval_strategy = 'steps'
            if getattr(args, 'eval_steps', None) is None: args.eval_steps = 0.1
        ga_steps = getattr(args, 'gradient_accumulation_steps', None)
        if ga_steps is not None and ga_steps > 1:
            from transformers import __version__ as transformers_version
            if Version(transformers_version) <= Version('4.45.2'):
                print('**** Unsloth: Please use our fixed gradient_accumulation_steps by updating transformers, TRL and Unsloth!\n'
                      '`pip install --upgrade --no-cache-dir --force-reinstall --no-deps unsloth transformers trl unsloth_zoo`')
        if getattr(args, 'eval_strategy', 'no') != 'no':
            eval_bsz = getattr(args, 'per_device_eval_batch_size', 8)
            if eval_bsz == 8 and args.per_device_train_batch_size < eval_bsz: args.per_device_eval_batch_size = args.per_device_train_batch_size
            if getattr(args, 'eval_accumulation_steps', None) is None and ga_steps is not None: args.eval_accumulation_steps = ga_steps
        fp16_full_eval = getattr(args, 'fp16_full_eval', False)
        if type(fp16_full_eval) is not bool: fp16_full_eval = False
        bf16_full_eval = getattr(args, 'bf16_full_eval', False)
        if type(bf16_full_eval) is not bool: bf16_full_eval = False
        if args.fp16 and bf16_full_eval: args.bf16_full_eval = False; args.fp16_full_eval = True
        if args.bf16 and fp16_full_eval: args.bf16_full_eval = True; args.fp16_full_eval = False
        if force_float32:
            args.bf16_full_eval = False
            args.fp16_full_eval = False
        elif os.environ.get('UNSLOTH_MIXED_PRECISION', 'float32') == 'bfloat16':
            args.bf16_full_eval = True
            args.fp16_full_eval = False
        elif not bf16_full_eval and not fp16_full_eval:
            args.bf16_full_eval = args.bf16
            args.fp16_full_eval = args.fp16
        _output_logits = False
        if locals().get('compute_metrics', None) is not None: _output_logits = True
        if locals().get('preprocess_logits_for_metrics', None) is not None: _output_logits = True
        if _output_logits:
            os.environ['UNSLOTH_RETURN_LOGITS'] = '1'
        if 'max_seq_length' not in locals() and not hasattr(args, 'max_seq_length'):
            pass
        else:
            model_max_seq_length = getattr(model, 'max_seq_length', None)
            args_max_seq_length  = getattr(args,  'max_seq_length', None)
            if args_max_seq_length is None and model_max_seq_length is not None:
                max_seq_length = model.max_seq_length
                if hasattr(args, 'max_seq_length'): args.max_seq_length = max_seq_length
            elif args_max_seq_length is not None and model_max_seq_length is not None:
                if args_max_seq_length > model_max_seq_length:
                    print('Unsloth: You set `max_seq_length` as ' + str(args_max_seq_length) + ' but '
                           'the maximum the model supports is ' + str(model_max_seq_length) + '. We shall reduce it.')
                    args.max_seq_length = model_max_seq_length
        if model is not None and hasattr(model, 'for_training'):
            model.for_training(use_gradient_checkpointing=getattr(args, 'gradient_checkpointing', True))
        if 'tokenizer' in locals() and hasattr(tokenizer, 'padding_side'): tokenizer.padding_side = 'right'
        if 'processing_class' in locals():
            if hasattr(processing_class, 'padding_side'): processing_class.padding_side = 'right'
            if hasattr(processing_class, 'tokenizer') and hasattr(processing_class.tokenizer, 'padding_side'): processing_class.tokenizer.padding_side = 'right'
        other_metrics = []
        if not isinstance(reward_funcs, list): _reward_funcs = [reward_funcs]
        else: _reward_funcs = reward_funcs
        for reward_func in _reward_funcs:
            try:
                reward_func_name = reward_func.__name__
                if True:
                    other_metrics.append(f'rewards/{reward_func_name}/mean')
                if True:
                    other_metrics.append(f'rewards/{reward_func_name}/std')
                if False:
                    other_metrics.append(f'rewards/{reward_func_name}')
            except: pass
        
        from unsloth_zoo.logging_utils import PatchRLStatistics
        PatchRLStatistics('grpo_trainer', other_metrics)
        
        # [TODO] Fix up DataParallel multiplying batch sizes
        # [TODO] DDP works, but DP seems to not work? [TODO]
        if getattr(args, "parallel_mode", None) == ParallelMode.NOT_DISTRIBUTED and args.n_gpu > 1:
            if getattr(args, "_n_gpu", 1) != 1:
                args._n_gpu = 1
        if "model" in locals() and hasattr(model, "for_training"):
            model.for_training(use_gradient_checkpointing=getattr(args, 'gradient_checkpointing', True))
        super().__init__(
            model = model,
            reward_funcs = reward_funcs,
            args = args,
            train_dataset = train_dataset,
            eval_dataset = eval_dataset,
            processing_class = processing_class,
            reward_processing_classes = reward_processing_classes,
            callbacks = callbacks,
            peft_config = peft_config,
            tools = tools,
            rollout_func = rollout_func,**kwargs)
        if "model" in locals() and hasattr(model, "for_inference"):
            model.for_inference()
        if hasattr(self, 'neftune_hook_handle'):
            self.neftune_hook_handle.remove()
            if hasattr(self, 'neftune_hook_handle'): del self.neftune_hook_handle
        if getattr(args, 'neftune_noise_alpha', None) is not None:
            model.get_input_embeddings().neftune_noise_alpha = self.neftune_noise_alpha
        pass
        if hasattr(self, 'accelerator'):
            scaler = self.accelerator.scaler
            current_model = model
            while hasattr(current_model, 'model'):
                current_model.accelerator_scaler = scaler
                current_model = current_model.model
            current_model.accelerator_scaler = scaler
        pass
        if hasattr(self, 'train'):
            self.train = MethodType(prepare_for_training_mode(self.__class__.train), self)
        pass
        if hasattr(self, 'llm') and self.llm is not None and hasattr(self.llm, 'get_tokenizer'):
            _vllm_tok = self.llm.get_tokenizer()
            _pc = getattr(self, 'processing_class', None) or getattr(self, 'tokenizer', None)
            if _vllm_tok is not None and _pc is not None and getattr(_pc, 'chat_template', None) is not None and getattr(_vllm_tok, 'chat_template', None) is None:
                _vllm_tok.chat_template = _pc.chat_template
        pass
        
pass


if hasattr(logger, "addFilter"):
    import logging
    class HideLoggingMessage(logging.Filter):
        def __init__(self, text): self.text = text
        def filter(self, x): return not (self.text in x.getMessage())
    pass
    logger.addFilter(HideLoggingMessage("`use_cache=True`"))

