from __future__ import division
import time
import torch 
import torch.nn as nn
from torch.autograd import Variable
import numpy as np
import cv2 
from util import *
import argparse
import os 
import os.path as osp
from darknet import Darknet
import pickle as pkl
import pandas as pd
import random

class PeopleDetector:
    def __init__(self, ):
        self.images = "imgs"
        self.batch_size = 1
        self.confidence = 0.5
        self.nms_thesh = 0.4
        self.start = 0
        self.CUDA = torch.cuda.is_available()
        self.weightsfile = "yolov3.weights"
        self.cfgfile = "cfg/yolov3.cfg"
        self.reso = 416
        self.det = "det"

        # ---- Set up the neural network ----
        # print("Loading network.....")

        self.num_classes = 80
        self.classes = load_classes("data/coco.names")
        
        self.model = Darknet(self.cfgfile)
        self.model.load_weights(self.weightsfile)
        print("Network successfully loaded")
        self.model.net_info["height"] = self.reso
        self.inp_dim = int(self.model.net_info["height"])
        assert self.inp_dim % 32 == 0
        assert self.inp_dim > 32
        # If there's a GPU availible, put the self.model on GPU
        if self.CUDA:
            self.model.cuda()
        # Set the self.model in evaluation mode
        self.model.eval()

    def write(self, x, results):
        c1 = tuple(x[1:3].int())
        c2 = tuple(x[3:5].int())
        img = results[int(x[0])]
        cls = int(x[-1])
        colors = pkl.load(open("pallete", "rb"))
        color = random.choice(colors)
        label = "{0}".format(self.classes[cls])
        cv2.rectangle(img, c1, c2, color, 1)
        t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_PLAIN, 1, 1)[0]
        c2 = c1[0] + t_size[0] + 3, c1[1] + t_size[1] + 4
        cv2.rectangle(img, c1, c2, color, -1)
        cv2.putText(img, label, (c1[0], c1[1] + t_size[1] + 4), cv2.FONT_HERSHEY_PLAIN, 1, [225, 255, 255], 1);
        return img

    def detect(self):
        read_dir = time.time()
        # Detection phase
        try:
            imlist = [osp.join(osp.realpath('.'), self.images, img) for img in os.listdir(self.images)]
        except NotADirectoryError:
            imlist = []
            imlist.append(osp.join(osp.realpath('.'), self.images))
        except FileNotFoundError:
            print("No file or directory with the name {}".format(self.images))
            exit()

        if not os.path.exists(self.det):
            os.makedirs(self.det)

        load_batch = time.time()
        loaded_ims = [cv2.imread(x) for x in imlist]

        im_batches = list(map(prep_image, loaded_ims, [self.inp_dim for x in range(len(imlist))]))
        im_dim_list = [(x.shape[1], x.shape[0]) for x in loaded_ims]
        im_dim_list = torch.FloatTensor(im_dim_list).repeat(1, 2)

        leftover = 0
        if (len(im_dim_list) % self.batch_size):
            leftover = 1

        if self.batch_size != 1:
            num_batches = len(imlist) // self.batch_size + leftover
            im_batches = [torch.cat((im_batches[i * self.batch_size: min((i + 1) * self.batch_size,
                                                                    len(im_batches))])) for i in range(num_batches)]

        write = 0

        if self.CUDA:
            im_dim_list = im_dim_list.cuda()

        start_det_loop = time.time()
        for i, batch in enumerate(im_batches):
            # load the image
            start = time.time()
            if self.CUDA:
                batch = batch.cuda()
            with torch.no_grad():
                prediction = self.model(Variable(batch), self.CUDA)

            prediction = write_results(prediction, self.confidence, self.num_classes, nms_conf=self.nms_thesh)

            end = time.time()

            if type(prediction) == int:
                # Prediction int == no Class founded
                for im_num, image in enumerate(imlist[i * self.batch_size: min((i + 1) * self.batch_size, len(imlist))]):
                    im_id = i * self.batch_size + im_num
                    print("{0:20s} predicted in {1:6.3f} seconds".format(image.split("/")[-1],
                                                                         (end - start) / self.batch_size))
                    print("{0:20s} {1:s}".format("Objects Detected:", ""))
                    print("----------------------------------------------------------")
                continue

            prediction[:, 0] += i * self.batch_size  # transform the atribute from index in batch to index in imlist

            if not write:  # If we have't initialised output
                output = prediction
                write = 1
            else:
                output = torch.cat((output, prediction))

            print("self.classes predicted")
            print(prediction[0, :])

            for im_num, image in enumerate(imlist[i * self.batch_size: min((i + 1) * self.batch_size, len(imlist))]):
                im_id = i * self.batch_size + im_num
                objs = [self.classes[int(x[-1])] for x in output if int(x[0]) == im_id]
                print("{0:20s} predicted in {1:6.3f} seconds".format(image.split("/")[-1], (end - start) / self.batch_size))
                print("{0:20s} {1:s}".format("Objects Detected:", " ".join(objs)))
                print("----------------------------------------------------------")

            if self.CUDA:
                torch.cuda.synchronize()
        try:
            output
        except NameError:
            print("No detections were made")
            exit()

        im_dim_list = torch.index_select(im_dim_list, 0, output[:, 0].long())

        scaling_factor = torch.min(416 / im_dim_list, 1)[0].view(-1, 1)

        output[:, [1, 3]] -= (self.inp_dim - scaling_factor * im_dim_list[:, 0].view(-1, 1)) / 2
        output[:, [2, 4]] -= (self.inp_dim - scaling_factor * im_dim_list[:, 1].view(-1, 1)) / 2

        output[:, 1:5] /= scaling_factor

        for i in range(output.shape[0]):
            output[i, [1, 3]] = torch.clamp(output[i, [1, 3]], 0.0, im_dim_list[i, 0])
            output[i, [2, 4]] = torch.clamp(output[i, [2, 4]], 0.0, im_dim_list[i, 1])

        output_recast = time.time()
        class_load = time.time()

        draw = time.time()

        list(map(lambda x: self.write(x, loaded_ims), output))

        det_names = pd.Series(imlist).apply(lambda x: "{}/det_{}".format(self.det, x.split("/")[-1]))

        list(map(cv2.imwrite, det_names, loaded_ims))

        end = time.time()

        print("SUMMARY")
        print("----------------------------------------------------------")
        print("{:25s}: {}".format("Task", "Time Taken (in seconds)"))
        print()
        print("{:25s}: {:2.3f}".format("Reading addresses", load_batch - read_dir))
        print("{:25s}: {:2.3f}".format("Loading batch", start_det_loop - load_batch))
        print("{:25s}: {:2.3f}".format("Detection (" + str(len(imlist)) + " images)", output_recast - start_det_loop))
        print("{:25s}: {:2.3f}".format("Output Processing", class_load - output_recast))
        print("{:25s}: {:2.3f}".format("Drawing Boxes", end - draw))
        print("{:25s}: {:2.3f}".format("Average time_per_img", (end - load_batch) / len(imlist)))
        print("----------------------------------------------------------")

        torch.cuda.empty_cache()


def main():
    det = PeopleDetector()
    det.detect()

if __name__ == "__main__":
    main()