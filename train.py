from __future__ import print_function
import argparse

import numpy as np
import six
from tqdm import tqdm
import time

import chainer
from chainer import cuda
import chainer.links as L
from chainer import optimizers

from model import HumanPartsNet
from debugger import Debugger
from data import MiniBatchLoader

resultdir = "./result/"
X_dir = "./data/img/"
y_dir = "./data/mask/"


def train(model, optimizer, MiniBatchLoader, mean_loss, ac):
    sum_accuracy, sum_loss = 0, 0
    model.train = True
    MiniBatchLoader.train = True
    for X, y in tqdm(MiniBatchLoader):
        x = chainer.Variable(xp.asarray(X, dtype=xp.float32), volatile='off')
        t = chainer.Variable(xp.asarray(y, dtype=xp.int32), volatile='off')
        # optimizer.weight_decay(0.0001)
        optimizer.update(model, x, t)
        sum_loss += float(model.loss.data) * len(t.data)
        sum_accuracy += float(model.accuracy) * len(t.data)
    print('train mean loss={}, accuracy={}'.format(sum_loss / MiniBatchLoader.datasize_train, sum_accuracy / MiniBatchLoader.datasize_train))
    mean_loss.append(sum_loss / MiniBatchLoader.datasize_train)
    ac.append(sum_accuracy / MiniBatchLoader.datasize_train)
    return model, optimizer, mean_loss, ac


def test(model, MiniBatchLoader, mean_loss, ac):
    sum_accuracy, sum_loss = 0, 0
    model.train = False
    MiniBatchLoader.train = False
    for X, y in tqdm(MiniBatchLoader):
        x = chainer.Variable(xp.asarray(X, dtype=xp.float32), volatile='on')
        t = chainer.Variable(xp.asarray(y, dtype=xp.int32), volatile='on')
        loss = model(x, t)
        sum_loss += float(loss.data) * len(t.data)
        sum_accuracy += float(model.accuracy) * len(t.data)
    print('test  mean loss={}, accuracy={}'.format(
        sum_loss / MiniBatchLoader.datasize_test, sum_accuracy / MiniBatchLoader.datasize_test))
    mean_loss.append(sum_loss / MiniBatchLoader.datasize_test)
    ac.append(sum_accuracy / MiniBatchLoader.datasize_test)
    return model, mean_loss, ac


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Human parts network')
    parser.add_argument('--batchsize', '-b', default=100, type=int,
                        help='Batch size of training')
    parser.add_argument('--epoch', '-e', default=100, type=int,
                        help='Number of epoch of training')
    parser.add_argument('--gpu', '-g', default=-1, type=int,
                        help='GPU ID (negative value indicates CPU)')
    parser.add_argument('--logflag', '-l', choices=('on', 'off'),
                        default='on', help='Writing and plotting result flag')
    parser.add_argument('--optimizer', '-o', choices=('adam', 'adagrad', 'sgd'),
                        default='sgd', help='Optimizer algorithm')
    parser.add_argument('--pretrainedmodel', '-p', default=None,
                        help='Path to pretrained model')
    parser.add_argument('--saveflag', '-s', choices=('on', 'off'),
                        default='off', help='Save model and optimizer flag')
    args = parser.parse_args()

    # model setteing
    model = HumanPartsNet(n_class=25)
    if args.pretrainedmodel is not None:
        from chainer import serializers
        serializers.load_npz(args.pretrainedmodel, model)

    # GPU settings
    if args.gpu >= 0:
        cuda.check_cuda_available()
        xp = cuda.cupy
        cuda.get_device(args.gpu).use()
        model.to_gpu()
    else: xp = np

    # Setup optimizer
    optimizer = optimizers.MomentumSGD(lr=1e-10, momentum=0.99)
    optimizer.setup(model)

    # prepare data feeder
    MiniBatchLoader = MiniBatchLoader(X_dir, y_dir, batchsize=args.batchsize, insize=model.insize, train=True)
    debugger = Debugger()

    # Learning loop
    train_ac, test_ac, train_mean_loss, test_mean_loss = [], [], [], []
    stime = time.clock()
    for epoch in six.moves.range(1, args.epoch + 1):
        print('Epoch', epoch, ': training...')
        model, optimizer, train_mean_loss, train_ac = train(model, optimizer, MiniBatchLoader, train_mean_loss, train_ac)
        print('Epoch', epoch, ': testing...')
        model, test_mean_loss, test_ac = test(model, MiniBatchLoader, test_mean_loss, test_ac)

        if args.logflag == 'on':
            etime = time.clock()
            debugger.writelog(MiniBatchLoader.datasize_train, MiniBatchLoader.datasize_test, MiniBatchLoader.batchsize,
                              'Human part segmentation', stime, etime,
                              train_mean_loss, train_ac, test_mean_loss, test_ac, epoch, LOG_FILENAME=resultdir + 'log.txt')
            debugger.plot_result(train_mean_loss, test_mean_loss, savename='log.png')
        if args.saveflag == 'on' and epoch % 10 == 0:
            from chainer import serializers
            serializers.save_hdf5(resultdir + 'humanpartsnet_epoch'+ str(epoch) + '.model', model)
            serializers.save_hdf5(resultdir + 'humanpartsnet_epoch'+ str(epoch) + '.state', optimizer)

