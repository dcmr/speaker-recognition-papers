import tensorflow as tf
import numpy as np
import os
import multiprocessing as mp
import sys


def clip_grad_by_value(tower_grad, clip_min, clip_max):
    grads, vars = zip(*tower_grad)
    grads_clip = [tf.clip_by_value(g, clip_value_min=clip_min, clip_value_max=clip_max) for g in grads]
    return zip(grads_clip, vars)

def clip_grad_by_norm(tower_grad, value):
    grads, vars = zip(*tower_grad)
    grads_clip = tf.clip_by_norm(grads, clip_norm=value)
    return zip(grads_clip, vars)

def average_gradients(tower_grads):
    average_grads = []
    for grad_and_vars in zip(*tower_grads):
        grads = [g for g, _ in grad_and_vars]
        grad = tf.stack(grads, 0)
        grad = tf.reduce_mean(grad, 0)
        v = grad_and_vars[0][1]
        grad_and_var = (grad, v)
        average_grads.append(grad_and_var)
    return average_grads


def feed_all_gpu(inp_dict, models, payload_per_gpu, batch_x, batch_y):
    for i in range(len(models)):
        x, y, _, _, _ = models[i]
        start_pos = i * payload_per_gpu
        stop_pos = (i + 1) * payload_per_gpu
        inp_dict[x] = batch_x[start_pos:stop_pos]
        inp_dict[y] = batch_y[start_pos:stop_pos]
    return inp_dict


def update_embeddings(vectors, embeddings, ys, config):
    for spkr in range(config.n_speaker):
        if len(embeddings[np.where(np.argmax(ys, 1) == spkr)]) != 0:
            vector = np.mean(embeddings[np.where(np.argmax(ys, 1) == spkr)], axis=0)
            if spkr in vectors.keys():
                vector = (vectors[spkr] + vector) / 2
            else:
                vector = vector
            vectors[spkr] = vector
        else:
            if spkr not in vectors.keys():
                vectors[spkr] = np.zeros(512, dtype=np.float32)
    return vectors


def system_gpu_status(config):
    if config.n_gpu == 0:
        os.environ['CUDA_VISIBLE_DEVICES'] = ""
    else:
        if os.path.exists('./tmp'):
            os.rename('./tmp', './tmp-backup')
        if sys.platform[:3] == 'win':
            os.system("powershell \"nvidia-smi -q -d Memory | Select-String Free > ./tmp\"")
            memory_gpu = open('tmp', 'r', encoding='utf-16').readlines()[1:-2]
            memory_gpu = [int(x.split()[2]) for x in memory_gpu]
            mem_ = []
            for i in range(len(memory_gpu)):
                if i%2 == 0:
                    mem_.append(memory_gpu[i])
            memory_gpu = mem_
        else:
            os.system('nvidia-smi -q -d Memory |grep -A4 GPU|grep Free > ./tmp')
            memory_gpu = [int(x.split()[2]) for x in open('tmp', 'r').readlines()]
        memory_gpu = np.array(memory_gpu, dtype=np.int32)
        gpu_list = []
        for _ in range(config.n_gpu):
            gpu_list.append(str(np.argmax(memory_gpu)))
            memory_gpu[np.argmax(memory_gpu)] = -10000
        s = ""
        for i in range(config.n_gpu):
            if i != 0:
                s += ','
            s += str(gpu_list[i])
        os.environ['CUDA_VISIBLE_DEVICES'] = s
        os.remove('./tmp')


def tower_to_collection(**kwargs):
    for key in kwargs.keys():
        tf.add_to_collection(key, kwargs[key])


def cosine(q, a, normalized=True, w=None, b=None, dis=False):
    if dis and (w or b):
        raise ValueError("`w`, `b` are `weight`, `bias` of cosine similarity.")
    w = w if w is not None else 1
    b = b if b is not None else 0
    if normalized:
        if dis:
            return 1 - tf.reduce_sum(q * a, -1, keepdims=True)
        return w * tf.reduce_sum(q * a, -1, keepdims=True)
    q_ = tf.sqrt(tf.reduce_sum(q ** 2, -1, keepdims=True) + 1e-10)
    a_ = tf.sqrt(tf.reduce_sum(a ** 2, -1, keepdims=True) + 1e-10)
    score = (w * tf.reduce_sum(q * a, -1, keepdims=True) + b) / q_ / a_
    if dis:
        score = 1 - score
    return score


def normalize(inputs):
    return inputs / tf.sqrt(tf.reduce_sum(inputs ** 2, axis=-1, keep_dims=True)+1e-10)


def calc_acc(score_mat, y_):
    return tf.reduce_sum(tf.cast(tf.equal(tf.reshape(tf.argmax(score_mat,
                                                               axis=-1, output_type=tf.int32),
                                                     (-1, 1)), y_), tf.int32)) / tf.shape(y_)[0]


def get_score_matrix():
    """"""


def multi_processing(func, jobs, proccess_num, use_list_params=False):
    with mp.Pool(proccess_num) as pool:
        if not use_list_params:
            res = pool.starmap(func, jobs)
        else:
            res = pool.map(func, jobs)
    return res
