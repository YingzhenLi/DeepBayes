from __future__ import print_function

import numpy as np
import tensorflow as tf
from mlp import mlp_layer

"""
generator p(y)p(z|y)p(x|z, y), GFY
"""
   
def deconv_layer(output_shape, filter_shape, activation, strides, name):
    scale = 1.0 / np.prod(filter_shape[:3])
    seed = int(np.random.randint(0, 1000))#123
    W = tf.Variable(tf.random_uniform(filter_shape, 
                             minval=-scale, maxval=scale, 
                             dtype=tf.float32, seed=seed), name = name+'_W')
    
    def apply(x):
        output_shape_x = (x.get_shape().as_list()[0],)+output_shape
        a = tf.nn.conv2d_transpose(x, W, output_shape_x, strides, 'SAME')
        if activation == 'relu':
            return tf.nn.relu(a)
        if activation == 'sigmoid':
            return tf.nn.sigmoid(a)
        if activation == 'linear':
            return a
        if activation == 'split':
            x1, x2 = tf.split(a, 2, 3)	# a is a 4-D tensor
            return tf.nn.sigmoid(x1), x2
            
    return apply

def generator(input_shape, dimH, dimZ, dimY, n_channel, last_activation, name):
    # first construct p(z|y)
    fc_layers = [dimY, dimH, dimZ*2]
    pzy_mlp_layers = []
    N_layers = len(fc_layers) - 1
    l = 0
    for i in range(N_layers):
        name_layer = name + '_pzy_l%d' % l
        if i+1 == N_layers:
            activation = 'linear'
        else:
            activation = 'relu'
        pzy_mlp_layers.append(mlp_layer(fc_layers[i], fc_layers[i+1], activation, name_layer))

    def pzy_params(y):
        out = y
        for layer in pzy_mlp_layers:
            out = layer(out)
        mu, log_sig = tf.split(out, 2, axis=1)
        return mu, log_sig

    # now construct p(x|z, y)
    filter_width = 5
    decoder_input_shape = [(4, 4, n_channel), (7, 7, n_channel), (14, 14, n_channel)]
    decoder_input_shape.append(input_shape)
    fc_layers = [dimZ+dimY, dimH, int(np.prod(decoder_input_shape[0]))]
    l = 0
    # first include the MLP
    mlp_layers = []
    N_layers = len(fc_layers) - 1
    for i in range(N_layers):
        name_layer = name + '_l%d' % l
        mlp_layers.append(mlp_layer(fc_layers[i], fc_layers[i+1], 'relu', name_layer))
        l += 1
    
    conv_layers = []
    N_layers = len(decoder_input_shape) - 1
    for i in range(N_layers):
        if i < N_layers - 1:
            activation = 'relu'
        else:
            activation = last_activation
        name_layer = name + '_l%d' % l
        output_shape = decoder_input_shape[i+1]
        input_shape = decoder_input_shape[i]
        up_height = int(np.ceil(output_shape[0]/float(input_shape[0])))
        up_width = int(np.ceil(output_shape[1]/float(input_shape[1])))
        strides = (1, up_height, up_width, 1)       
        if activation in ['logistic_cdf', 'gaussian'] and i == N_layers - 1:	# ugly wrapping for logistic cdf likelihoods
            activation = 'split'
            output_shape = (output_shape[0], output_shape[1], output_shape[2]*2)
        
        filter_shape = (filter_width, filter_width, output_shape[-1], input_shape[-1])
        
        conv_layers.append(deconv_layer(output_shape, filter_shape, activation, \
                                            strides, name_layer))
        l += 1
    
    print('decoder shared Conv Net of size', decoder_input_shape)
    
    def pxzy_params(z, y):
        x = tf.concat([z, y], 1)
        for layer in mlp_layers:
            x = layer(x)
        x = tf.reshape(x, (x.get_shape().as_list()[0],)+decoder_input_shape[0])
        for layer in conv_layers:
            x = layer(x)
        return x
        
    return pzy_params, pxzy_params

def sample_gaussian(mu, log_sig):
    return mu + tf.exp(log_sig) * tf.random_normal(mu.get_shape())

def construct_gen(gen, dimZ, dimY):
    def gen_data(y, sampling=True):
        # start from sample z_0, generate data
        pzy, pxzy = gen
        mu, log_sig = pzy(y)
        if sampling:
            z = sample_gaussian(mu, log_sig)
        else:
            z = mu
        x = pxzy(z, y)
        if type(x) == list or type(x) == tuple:	# split stuff
            return x[0]
        else:  
            return x

    return gen_data
    
