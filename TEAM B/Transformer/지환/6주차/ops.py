### X:AI 6주차 Code 과제
### AI빅데이터융합경영 배지환 

import pickle
import numpy as np
import torch
import torch.nn as nn

pickle_eng = open('pickles/eng.pickle', 'rb')
eng = pickle.load(pickle_eng)
pad_idx = eng.vocab.stoi['<pad>']
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# masking 행렬 생성
def create_subsequent_mask(target):
    # input target 배치 크기와 길이
    batch_size, target_length = target.size()

    # torch.triu 함수로 대각선 아래 값들을 0으로하는 상삼각행렬 생성 > boolean 타입으로 변경 
    subsequent_mask = torch.triu(torch.ones(target_length, target_length), diagonal=1).bool().to(device)

    # 배치 size만큼 복제하여 모든 데이터에 적용 가능하게 변경
    subsequent_mask = subsequent_mask.unsqueeze(0).repeat(batch_size, 1, 1)

    return subsequent_mask


def create_source_mask(source):
    # input source 길이
    source_length = source.shape[1]

    # padding token 위치 True인 boolean tensor 생성
    source_mask = (source == pad_idx)

    # source 길이만큼 복제하여 모든 데이터에 적용 가능하게 변경
    source_mask = source_mask.unsqueeze(1).repeat(1, source_length, 1)

    return source_mask


def create_target_mask(source, target):
    # target sequence 길이
    target_length = target.shape[1]

    # masking tensor 생성
    subsequent_mask = create_subsequent_mask(target)

    # 입력(source) 및 출력(target) 시퀀스에서 패딩(padding)된 부분을 True로 표시하는 Boolean 텐서를 생성
    source_mask = (source == pad_idx)
    target_mask = (target == pad_idx)

    # target sequence 길이만큼 복제하여 적용할 수 있도록 배치 차원을 추가
    dec_enc_mask = source_mask.unsqueeze(1).repeat(1, target_length, 1) # 첫 번째 차원(dim=1)을 기준으로 확장(unsqueeze(1))하여 각 타겟 시퀀스 위치마다 복제(repeat(1, target_length, 1))
    target_mask = target_mask.unsqueeze(1).repeat(1, target_length, 1) # 마찬가지로 확장하고 target_length 만큼 복제

    # 미래 위치 마스킹
    # OR 연산으로 결합 / decoder가 패딩된 위치 또는 미래의 위치를 참조하지 않도록 마스크를 최종 조정
    target_mask = target_mask | subsequent_mask

    # target_mask = decoder의 self attention에 쓰임
    # dec_enc_mask = decoder의 dec enc attention에 쓰임
    return target_mask, dec_enc_mask

# 주어진 문장에 대해 위치 정보를 나타내는 벡터 생성
def create_position_vector(sentence):
    # 입력 문장 크기
    batch_size, _ = sentence.size()
    # 각 단어 위치 벡터 생성
    pos_vec = np.array([(pos+1) if word != pad_idx else 0 # padding token인 경우 0으로 설정
                        for row in range(batch_size) for pos, word in enumerate(sentence[row])])
    # batch size에 맞게 조정
    pos_vec = pos_vec.reshape(batch_size, -1) # -1 = 나머지 차원 자동 설정
    pos_vec = torch.LongTensor(pos_vec).to(device)
    return pos_vec


def create_positional_encoding(max_len, hidden_dim):
    # PE(pos, 2i)     = sin(pos/10000 ** (2*i / hidden_dim))
    # PE(pos, 2i + 1) = cos(pos/10000 ** (2*i / hidden_dim))

    # positional encoding table 생성
    # pos/10000 ** (2*i / hidden_dim) 먼저 계산
    sinusoid_table = np.array([pos / np.power(10000, 2 * i / hidden_dim)
                               for pos in range(max_len) for i in range(hidden_dim)])

    sinusoid_table = sinusoid_table.reshape(max_len, -1)

    # sin, cos 계산
    sinusoid_table[:, 0::2] = np.sin(sinusoid_table[:, 0::2])  # 짝수열
    sinusoid_table[:, 1::2] = np.cos(sinusoid_table[:, 1::2])  # 홀수열

    # numpy 배열 tensor로 변환
    sinusoid_table = torch.FloatTensor(sinusoid_table).to(device)
    sinusoid_table[0] = 0. # padding token 위치 표시

    return sinusoid_table

# 가중치 초기화 함수
def init_weight(layer):
    nn.init.xavier_uniform_(layer.weight)
    if layer.bias is not None: # bias 있으면 0으로 초기화
        nn.init.constant_(layer.bias, 0)