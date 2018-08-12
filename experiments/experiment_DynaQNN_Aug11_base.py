# System built-in modules
import time
from datetime import datetime
import sys
import os
from multiprocessing import Pool
# Project dependency modules
import pandas as pd
pd.set_option('mode.chained_assignment', None)  # block warnings due to DataFrame value assignment
import lasagne
# Project modules
sys.path.append('../')
from sleep_control.traffic_emulator import TrafficEmulator
from sleep_control.traffic_server import TrafficServer
from sleep_control.controller import QController, DummyController, NController
from sleep_control.integration import Emulation
from sleep_control.env_models import SJTUModel
from rl.qtable import QAgent
from rl.qnn_theano import QAgentNN
from rl.mixin import PhiMixin, DynaMixin


sys_stdout = sys.stdout
FLAG = sys.argv[2]
filecnt = sys.argv[3]
log_prefix = '_'.join(['msg'] + os.path.basename(__file__).split('_')[1:3] + [FLAG,str(filecnt)])
log_file_name = "{}_{}.log".format(log_prefix, sys.argv[1])

# Composite classes
class Phi_QAgentNN(PhiMixin, QAgentNN):
    def __init__(self, **kwargs):
        super(Phi_QAgentNN, self).__init__(**kwargs)

class Dyna_QAgent(DynaMixin, QAgent):
    def __init__(self, **kwargs):
        super(Dyna_QAgent, self).__init__(**kwargs)

class Dyna_QAgentNN(DynaMixin, QAgentNN):
    def __init__(self, **kwargs):
        super(Dyna_QAgentNN, self).__init__(**kwargs)


# load from processed data
session_df =pd.read_csv(
    filepath_or_buffer='../cellular_traffic/%s%03d.csv'%(FLAG,int(filecnt)),
    parse_dates=['startTime_datetime', 'endTime_datetime']
)

timefile = open('../cellular_traffic/time.txt')
timelist = timefile.readlines.split('\n')

# Parameters
# |- Agent
#    |- QAgent
actions = [(True, None), (False, 'serve_all')]
gamma, alpha = 0.9, 0.9  # TD backup
explore_strategy, epsilon = 'epsilon', 0.02  # exploration
#    |- QAgentNN
#        | - Phi
# phi_length = 5
# dim_state = (1, phi_length, 3+2)
# range_state_slice = [(0, 10), (0, 10), (0, 10), (0, 1), (0, 1)]
# range_state = [[range_state_slice]*phi_length]
#        | - No Phi
phi_length = 0
dim_state = (1, 1, 3)
range_state = ((((0, 10), (0, 10), (0, 10)),),)
#        | - Other params
momentum, learning_rate = 0.9, 0.01  # SGD
num_buffer, memory_size, batch_size, update_period, freeze_period  = 2, 200, 100, 4, 16
reward_scaling, reward_scaling_update, rs_period = 1, 'adaptive', 32  # reward scaling
#    |- Env model
model_type, traffic_window_size = 'IPP', 50
stride, n_iter, adjust_offset = 2, 3, 1e-22
eval_period, eval_len = 4, 100
n_belief_bins, max_queue_len = 0, 20
Rs, Rw, Rf, Co, Cw = 1.0, -1.0, -10.0, -5.0, -0.5
traffic_params = (model_type, traffic_window_size,
                  stride, n_iter, adjust_offset,
                  eval_period, eval_len,
                  n_belief_bins)
queue_params = (max_queue_len,)
beta = 0.5  # R = (1-beta)*ServiceReward + beta*Cost
reward_params = (Rs, Rw, Rf, Co, Cw, beta)
#    |- DynaQ
num_sim = 1

# |- Env
#    |- Time
# start_time = pd.to_datetime("2014-10-15 09:40:00")
start_time = pd.to_datetime(timelist[filecnt*2])
tail_datetime = pd.to_datetime(timelist[filecnt*2+1])
# total_time = pd.Timedelta(hours=2)
total_time = tail_datetime - start_time
time_step = pd.Timedelta(seconds=2)
backoff_epochs = num_buffer*memory_size+phi_length
head_datetime =  start_time - time_step*backoff_epochs
tail_datetime = head_datetime + total_time
TOTAL_EPOCHS = int(total_time/time_step)
#    |- Reward
rewarding = {'serve': Rs, 'wait': Rw, 'fail': Rf}

te = TrafficEmulator(
    session_df=session_df, time_step=time_step,
    head_datetime=head_datetime, tail_datetime=tail_datetime,
    rewarding=rewarding,
    verbose=2)

ts = TrafficServer(cost=(Co, Cw), verbose=2)

env_model = SJTUModel(traffic_params, queue_params, reward_params, 2)

agent = Dyna_QAgentNN(
    env_model=env_model, num_sim=num_sim,
# agent = Phi_QAgentNN(
#     phi_length=phi_length,
    dim_state=dim_state, range_state=range_state,
    f_build_net = None,
    batch_size=batch_size, learning_rate=learning_rate, momentum=momentum,
    reward_scaling=reward_scaling, reward_scaling_update=reward_scaling_update, rs_period=rs_period,
    update_period=update_period, freeze_period=freeze_period,
    memory_size=memory_size, num_buffer=num_buffer,
# Below is QAgent params
    actions=actions, alpha=alpha, gamma=gamma,
    explore_strategy=explore_strategy, epsilon=epsilon,
    verbose=2)

c = QController(agent=agent)

emu = Emulation(te=te, ts=ts, c=c, beta=beta)

# Heavyliftings
t = time.time()
sys.stdout = sys_stdout
log_path = './log/'
if os.path.isfile(log_path+log_file_name):
    print "Log file {} already exist. Experiment cancelled.".format(log_file_name)
else:
    log_file = open(log_path+log_file_name,"w")
    log_file_temp = open(log_path+log_file_name+'temp',"w")
    print datetime.now().strftime('[%Y-%m-%d %H:%M:%S]'),
    print '{}%'.format(int(100.0*emu.epoch/TOTAL_EPOCHS)),
    print log_file_name
    time.sleep(1)
    sys.stdout = log_file
    while emu.epoch is not None and emu.epoch<TOTAL_EPOCHS:
        # log time
        if emu.epoch < TOTAL_EPOCHS / 2:
            sys.stdout = log_File_temp 
        else:
            sys.stdout = log_file 
            emu.c.agent.EPSILON = 0 
        print "Epoch {},".format(emu.epoch),
        left = emu.te.head_datetime + emu.te.epoch*emu.te.time_step
        right = left + emu.te.time_step
        print "{} - {}".format(left.strftime("%Y-%m-%d %H:%M:%S"), right.strftime("%Y-%m-%d %H:%M:%S"))
        emu.step()
        print
        if emu.epoch%(0.05*TOTAL_EPOCHS)==0:
            sys.stdout = sys_stdout
            print datetime.now().strftime('[%Y-%m-%d %H:%M:%S]'),
            print '{}%'.format(int(100.0*emu.epoch/TOTAL_EPOCHS)),
            print log_file_name
            time.sleep(1)
            sys.stdout = log_file
    sys.stdout = sys_stdout
    log_file.close()
    print
    print log_file_name,
    print '{:.3f} sec,'.format(time.time()-t),
    print '{:.3f} min'.format((time.time()-t)/60)

