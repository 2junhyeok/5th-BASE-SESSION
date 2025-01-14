import os
import numpy as np

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms, datasets

## 트레이닝 파라미터 설정하기
lr = 1e-3
batch_size = 4
num_epoch = 100

data_dir = './datasets' # 데이터가 저장되어 있는 디렉토리
ckpt_dir = './checkpoint' # 학습된 네트워크가 저장될 디렉토리
log_dir = './log' # 텐서보드 로그 파일이 저장될 디렉토리

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

## 네트워크 구축하기
class UNet(nn.Module):
    # U-net의 필요한 layer 선언
    def __init__(self):
        super(UNet, self).__init__()

        # 총 6개의 argument로 구성된 CBR2d Func 정의 # 패딩 제거 !! 
        def CBR2d(in_channels, out_channels, kernel_size=3, stride=1, bias=True):
            layers = []
            # convolution layer 정의
            layers += [nn.Conv2d(in_channels=in_channels, out_channels=out_channels,
                                 kernel_size=kernel_size, stride=stride, 
                                 bias=bias)]
            # batchnorm layer 정의
            layers += [nn.BatchNorm2d(num_features=out_channels)]
            # ReLU layer 정의
            layers += [nn.ReLU()]

            cbr = nn.Sequential(*layers)

            return cbr

        # Contracting path
        self.enc1_1 = CBR2d(in_channels=1, out_channels=64)
        self.enc1_2 = CBR2d(in_channels=64, out_channels=64)

        self.pool1 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.enc2_1 = CBR2d(in_channels=64, out_channels=128)
        self.enc2_2 = CBR2d(in_channels=128, out_channels=128)

        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.enc3_1 = CBR2d(in_channels=128, out_channels=256)
        self.enc3_2 = CBR2d(in_channels=256, out_channels=256)

        self.pool3 = nn.MaxPool2d(kernel_size=2, stride=2)

        self.enc4_1 = CBR2d(in_channels=256, out_channels=512)
        self.enc4_2 = CBR2d(in_channels=512, out_channels=512)

        self.pool4 = nn.MaxPool2d(kernel_size=2, stride=2) 

        # Bottlneck 구간 ?
        self.enc5_1 = CBR2d(in_channels=512, out_channels=1024)

        # Expansive path # channel 수를 감소 시키며 Up-Convolution
        self.dec5_1 = CBR2d(in_channels=1024, out_channels=512)

        # up-conv 2x2 
        self.unpool4 = nn.ConvTranspose2d(in_channels=512, out_channels=512,
                                          kernel_size=2, stride=2, bias=True)

        self.dec4_2 = CBR2d(in_channels=2 * 512, out_channels=512) # 첫 번재 decoder 파트는 두 배가 됨
        self.dec4_1 = CBR2d(in_channels=512, out_channels=256)

        self.unpool3 = nn.ConvTranspose2d(in_channels=256, out_channels=256,
                                          kernel_size=2, stride=2, bias=True)

        # skip-connection으로 연결되는 볼륨이 추가적으로 존재하기 때문에 인풋 채널을 2배
        self.dec3_2 = CBR2d(in_channels=2 * 256, out_channels=256) 
        self.dec3_1 = CBR2d(in_channels=256, out_channels=128)

        self.unpool2 = nn.ConvTranspose2d(in_channels=128, out_channels=128,
                                          kernel_size=2, stride=2, bias=True)

        self.dec2_2 = CBR2d(in_channels=2 * 128, out_channels=128)
        self.dec2_1 = CBR2d(in_channels=128, out_channels=64)

        self.unpool1 = nn.ConvTranspose2d(in_channels=64, out_channels=64,
                                          kernel_size=2, stride=2, bias=True)

        self.dec1_2 = CBR2d(in_channels=2 * 64, out_channels=64)
        self.dec1_1 = CBR2d(in_channels=64, out_channels=64)

        # segmentation에 필요한 n개의 클래스에 대한 아웃풋을 만들어주기 위해 1x1 conv layer 추가
        self.fc = nn.Conv2d(in_channels=64, out_channels=1, kernel_size=1, stride=1, bias=True)
        # 논문 구조상 output = 2 channel
	    # train 데이터에서 세포 / 배경을 검출하는것이 목표여서 class_num = 1로 지정
     
    # init func에서 생성한 U-net 레이어들을 연결
    def forward(self, x): # x는 input img 
        # Contracting path
        enc1_1 = self.enc1_1(x) 
        enc1_2 = self.enc1_2(enc1_1)
        pool1 = self.pool1(enc1_2)

        enc2_1 = self.enc2_1(pool1)
        enc2_2 = self.enc2_2(enc2_1)
        pool2 = self.pool2(enc2_2)

        enc3_1 = self.enc3_1(pool2)
        enc3_2 = self.enc3_2(enc3_1)
        pool3 = self.pool3(enc3_2)

        enc4_1 = self.enc4_1(pool3)
        enc4_2 = self.enc4_2(enc4_1)
        pool4 = self.pool4(enc4_2)

        enc5_1 = self.enc5_1(pool4)

        # Expanding path
        dec5_1 = self.dec5_1(enc5_1)

        unpool4 = self.unpool4(dec5_1)
        # cat: 채널 방향으로 연결하는 함수
        # dim = [0: batch, 1: channel, 2: height, 3: width]
        cat4 = torch.cat((unpool4, enc4_2), dim=1) 
        dec4_2 = self.dec4_2(cat4)
        dec4_1 = self.dec4_1(dec4_2)

        unpool3 = self.unpool3(dec4_1)
        cat3 = torch.cat((unpool3, enc3_2), dim=1)
        dec3_2 = self.dec3_2(cat3)
        dec3_1 = self.dec3_1(dec3_2)

        unpool2 = self.unpool2(dec3_1)
        cat2 = torch.cat((unpool2, enc2_2), dim=1)
        dec2_2 = self.dec2_2(cat2)
        dec2_1 = self.dec2_1(dec2_2)

        unpool1 = self.unpool1(dec2_1)
        cat1 = torch.cat((unpool1, enc1_2), dim=1)
        dec1_2 = self.dec1_2(cat1)
        dec1_1 = self.dec1_1(dec1_2)

        x = self.fc(dec1_1)

        return x
