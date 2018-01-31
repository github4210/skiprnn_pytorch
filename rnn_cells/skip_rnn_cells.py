import torch
import torch.nn.functional as F
import torch.nn as nn
import numpy as np

def SkipLSTMCell(input, hidden, num_layers, w_ih, w_hh, w_uh,b_ih=None, b_hh=None, b_uh=None,
                  activation=F.tanh, layer_norm=False):
    if num_layers != 1:
        raise RuntimeError("wrong num_layers: got {}, expected {}".format(num_layers, 1))
    w_ih, w_hh = w_ih[0], w_hh[0]
    b_ih = b_ih[0] if b_ih is not None else None
    b_hh = b_hh[0] if b_hh is not None else None

    c_prev, h_prev, update_prob_prev, cum_update_prob_prev = hidden

    gates = F.linear(input, w_ih, b_ih) + F.linear(h_prev, w_hh, b_hh)

    ingate, forgetgate, cellgate, outgate = gates.chunk(4, 1)

    if layer_norm:
        if ingate.is_cuda:
            ingate = nn.BatchNorm1d(ingate.shape[1]).cuda()(ingate.contiguous())
            forgetgate = nn.BatchNorm1d(forgetgate.shape[1]).cuda()(forgetgate.contiguous())
            cellgate = nn.BatchNorm1d(cellgate.shape[1]).cuda()(cellgate.contiguous())
            outgate = nn.BatchNorm1d(outgate.shape[1]).cuda()(outgate.contiguous())
        else:
            ingate = nn.BatchNorm1d(ingate.shape[1])(ingate.contiguous())
            forgetgate = nn.BatchNorm1d(forgetgate.shape[1])(forgetgate.contiguous())
            cellgate = nn.BatchNorm1d(cellgate.shape[1])(cellgate.contiguous())
            outgate = nn.BatchNorm1d(outgate.shape[1])(outgate.contiguous())

    ingate = F.sigmoid(ingate)
    forgetgate = F.sigmoid(forgetgate)
    cellgate = activation(cellgate)
    outgate = F.sigmoid(outgate)

    new_c_tilde = (forgetgate * c_prev) + (ingate * cellgate)
    new_h_tilde = outgate * activation(new_c_tilde)
    # Compute value for the update prob
    new_update_prob_tilde = F.sigmoid(F.linear(new_c_tilde, w_uh, b_uh))
    # Compute value for the update gate
    cum_update_prob = cum_update_prob_prev + torch.min(update_prob_prev, 1. - cum_update_prob_prev)
    update_gate = cum_update_prob.round()
    # Apply update gate
    new_c = update_gate * new_c_tilde + (1. - update_gate) * c_prev
    new_h = update_gate * new_h_tilde + (1. - update_gate) * h_prev
    new_update_prob = update_gate * new_update_prob_tilde + (1. - update_gate) * update_prob_prev
    new_cum_update_prob = update_gate * 0. + (1. - update_gate) * cum_update_prob

    new_state = (new_c, new_h, new_update_prob, new_cum_update_prob)
    new_output = (new_h, update_gate)

    return new_output, new_state


######################################################
######################################################

def SkipGRUCell(input, state, num_layers, w_ih, w_hh, w_uh,b_ih=None, b_hh=None, b_uh=None,
                  activation=F.tanh, layer_norm=False):

    if num_layers != 1:
        raise RuntimeError("wrong num_layers: got {}, expected {}".format(num_layers, 1))
    w_ih, w_hh = w_ih[0], w_hh[0]
    b_ih = b_ih[0] if b_ih is not None else None
    b_hh = b_hh[0] if b_hh is not None else None

    h_prev, update_prob_prev, cum_update_prob_prev = state

    gi = F.linear(input, w_ih, b_ih)
    gh = F.linear(h_prev, w_hh, b_hh)
    i_r, i_i, i_n = gi.chunk(3, 1)
    h_r, h_i, h_n = gh.chunk(3, 1)

    resetgate_tmp = i_r + h_r
    inputgate_tmp = i_i + h_i
    if layer_norm:
        if inputgate_tmp.is_cuda:
            resetgate_tmp = nn.BatchNorm1d(resetgate_tmp.shape[1]).cuda()(resetgate_tmp.contiguous())
            inputgate_tmp = nn.BatchNorm1d(inputgate_tmp.shape[1]).cuda()(inputgate_tmp.contiguous())
        else:
            resetgate_tmp = nn.BatchNorm1d(resetgate_tmp.shape[1])(resetgate_tmp.contiguous())
            inputgate_tmp = nn.BatchNorm1d(inputgate_tmp.shape[1])(inputgate_tmp.contiguous())

    resetgate = F.sigmoid(resetgate_tmp)
    inputgate = F.sigmoid(inputgate_tmp)
    newgate = activation(i_n + resetgate * h_n)
    new_h_tilde = newgate + inputgate * (h_prev - newgate)

    # Compute value for the update prob
    new_update_prob_tilde = F.sigmoid(F.linear(new_h_tilde, w_uh, b_uh))
    # Compute value for the update gate
    cum_update_prob = cum_update_prob_prev + torch.min(update_prob_prev, 1. - cum_update_prob_prev)
    update_gate = cum_update_prob.round()
    # Apply update gate
    new_h = update_gate * new_h_tilde + (1. - update_gate) * h_prev
    new_update_prob = update_gate * new_update_prob_tilde + (1. - update_gate) * update_prob_prev
    new_cum_update_prob = update_gate * 0. + (1. - update_gate) * cum_update_prob

    new_state = (new_h, new_update_prob, new_cum_update_prob)
    new_output = (new_h, update_gate)

    return new_output, new_state

######################################################
######################################################

def MultiSkipLSTMCell(input, state, num_layers, w_ih, w_hh, w_uh,b_ih=None, b_hh=None, b_uh=None,
                  activation=F.tanh, layer_norm=False):

    _, _ , update_prob_prev, cum_update_prob_prev = state[-1]
    cell_input = input
    state_candidates = []

    for idx in np.arange(num_layers):
        c_prev, h_prev, _, _ = state[idx]

        gates = F.linear(cell_input, w_ih[idx], b_ih[idx]) + F.linear(h_prev, w_hh[idx], b_hh[idx])

        ingate, forgetgate, cellgate, outgate = gates.chunk(4, 1)

        if layer_norm:
            if ingate.is_cuda:
                ingate = nn.BatchNorm1d(ingate.shape[1]).cuda()(ingate.contiguous())
                forgetgate = nn.BatchNorm1d(forgetgate.shape[1]).cuda()(forgetgate.contiguous())
                cellgate = nn.BatchNorm1d(cellgate.shape[1]).cuda()(cellgate.contiguous())
                outgate = nn.BatchNorm1d(outgate.shape[1]).cuda()(outgate.contiguous())
            else:
                ingate = nn.BatchNorm1d(ingate.shape[1])(ingate.contiguous())
                forgetgate = nn.BatchNorm1d(forgetgate.shape[1])(forgetgate.contiguous())
                cellgate = nn.BatchNorm1d(cellgate.shape[1])(cellgate.contiguous())
                outgate = nn.BatchNorm1d(outgate.shape[1])(outgate.contiguous())

        ingate = F.sigmoid(ingate)
        forgetgate = F.sigmoid(forgetgate)
        cellgate = activation(cellgate)
        outgate = F.sigmoid(outgate)

        new_c_tilde = (forgetgate * c_prev) + (ingate * cellgate)
        new_h_tilde = outgate * activation(new_c_tilde)

        state_candidates.append((new_c_tilde,new_h_tilde))
        cell_input = new_h_tilde

    # Compute value for the update prob
    new_update_prob_tilde = F.sigmoid(F.linear(state_candidates[-1][0], w_uh, b_uh))

    # Compute value for the update gate
    cum_update_prob = cum_update_prob_prev + torch.min(update_prob_prev, 1. - cum_update_prob_prev)
    update_gate = cum_update_prob.round()

    # Apply update gate
    new_states = []
    for idx in np.arange(num_layers - 1):
        new_c = update_gate * state_candidates[idx][0] + (1. - update_gate) * state[idx][0]
        new_h = update_gate * state_candidates[idx][1] + (1. - update_gate) * state[idx][1]
        new_states.append((new_c,new_h,None,None))
    new_c = update_gate * state_candidates[-1][0] + (1. - update_gate) * state[-1][0]
    new_h = update_gate * state_candidates[-1][1] + (1. - update_gate) * state[-1][1]

    new_update_prob = update_gate * new_update_prob_tilde + (1. - update_gate) * update_prob_prev
    new_cum_update_prob = update_gate * 0. + (1. - update_gate) * cum_update_prob
    new_states.append((new_c, new_h, new_update_prob, new_cum_update_prob))
    new_output = (new_h, update_gate)

    return new_output, new_states

######################################################
######################################################

def MultiSkipGRUCell(input, state, num_layers, w_ih, w_hh, w_uh,b_ih=None, b_hh=None, b_uh=None,
                  activation=F.tanh, layer_norm=False):

    _ , update_prob_prev, cum_update_prob_prev = state[-1]
    cell_input = input
    state_candidates = []

    for idx in np.arange(num_layers):

        h_prev, _, _ = state[idx]

        gi = F.linear(cell_input, w_ih[idx], b_ih[idx])
        gh = F.linear(h_prev, w_hh[idx], b_hh[idx])
        i_r, i_i, i_n = gi.chunk(3, 1)
        h_r, h_i, h_n = gh.chunk(3, 1)

        resetgate_tmp = i_r + h_r
        inputgate_tmp = i_i + h_i
        if layer_norm:
            if inputgate_tmp.is_cuda:
                resetgate_tmp = nn.BatchNorm1d(resetgate_tmp.shape[1]).cuda()(resetgate_tmp.contiguous())
                inputgate_tmp = nn.BatchNorm1d(inputgate_tmp.shape[1]).cuda()(inputgate_tmp.contiguous())
            else:
                resetgate_tmp = nn.BatchNorm1d(resetgate_tmp.shape[1])(resetgate_tmp.contiguous())
                inputgate_tmp = nn.BatchNorm1d(inputgate_tmp.shape[1])(inputgate_tmp.contiguous())

        resetgate = F.sigmoid(resetgate_tmp)
        inputgate = F.sigmoid(inputgate_tmp)
        newgate = activation(i_n + resetgate * h_n)
        new_h_tilde = newgate + inputgate * (h_prev - newgate)

        state_candidates.append(new_h_tilde)
        cell_input = new_h_tilde

    # Compute value for the update prob
    new_update_prob_tilde = F.sigmoid(F.linear(state_candidates[-1], w_uh, b_uh))

    # Compute value for the update gate
    cum_update_prob = cum_update_prob_prev + torch.min(update_prob_prev, 1. - cum_update_prob_prev)
    update_gate = cum_update_prob.round()

    # Apply update gate
    new_states = []
    for idx in np.arange(num_layers - 1):
        new_h = update_gate * state_candidates[idx] + (1. - update_gate) * state[idx][0]
        new_states.append((new_h,None,None))
    new_h = update_gate * state_candidates[-1] + (1. - update_gate) * state[-1][0]

    new_update_prob = update_gate * new_update_prob_tilde + (1. - update_gate) * update_prob_prev
    new_cum_update_prob = update_gate * 0. + (1. - update_gate) * cum_update_prob
    new_states.append((new_h, new_update_prob, new_cum_update_prob))
    new_output = (new_h, update_gate)

    return new_output, new_states
