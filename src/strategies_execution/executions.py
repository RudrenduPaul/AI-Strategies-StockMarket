# -*- coding: utf-8 -*-

import pandas as pd
import numpy as np
import math
# Just disables the warning, doesn't enable AVX/FMA
import os
import sys, getopt
from datetime import datetime, timedelta

from sklearn.preprocessing import StandardScaler

import utils.func_utils as func_utils

# Import classes
import classes.myCerebro as myCerebro
import classes.myAnalyzer as myAnalyzer
import classes.model as model
import classes.geneticRepresentation as geneticRepresentation

# Import strategies execution
import strategies_execution.execution_analysis as execution_analysis
import strategies_execution.execution_plot as execution_plot

# Import strategies
from strategies.buy_and_hold_strategy import BuyAndHoldStrategy
from strategies.classic_strategy import ClassicStrategy
from strategies.neural_network_strategy import NeuralNetworkStrategy
from strategies.combined_signal_strategy import CombinedSignalStrategy

import pyswarms as ps

import backtrader as bt
import backtrader.plot
import matplotlib
import matplotlib.pyplot as plt

from numpy.random import seed

import warnings

if not sys.warnoptions:
    warnings.simplefilter("ignore")

seed(1)
# Opciones de ejecucion
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
pd.options.mode.chained_assignment = None
np.set_printoptions(threshold=sys.maxsize)


def print_execution_name(execution_name):
    print("\n --------------- ", execution_name, " --------------- \n")


def execute_strategy(strategy, df, commission):
    # Creamos la instancia cerebro
    cerebro = myCerebro.MyCerebro()

    # Añadimos la estrategia al cerebro
    cerebro.addstrategy(strategy)

    # Añadimos los datos al cerebro
    data = bt.feeds.PandasData(dataname = df)
    cerebro.adddata(data)

    # Añadimos los analizadores
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawDown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="tradeAnalyzer")
    cerebro.addanalyzer(myAnalyzer.MyAnalyzer, _name = "myAnalyzer")

    # Fijamos el dinero inicial y la comisión
    cerebro.broker.setcash(6000.0)
    cerebro.broker.setcommission(commission=commission)

    initial_value = cerebro.broker.getvalue()

    print('\nValor inicial de la cartera: %.2f' % initial_value)

    # Ejecutamos la estrategia sobre los datos del test
    strats = cerebro.run()

    final_value = cerebro.broker.getvalue()

    print('Valor final de la cartera  : %.2f' % final_value)

    # print the analyzers
    dd = strats[0].analyzers.drawDown.get_analysis()
    ta = strats[0].analyzers.tradeAnalyzer.get_analysis()
    ma = strats[0].analyzers.myAnalyzer.get_analysis()

    return cerebro, initial_value, final_value, ta, dd, ma


def execute_buy_and_hold_strategy(df, commission, data_name, start_date, end_date):

    print_execution_name("Estrategia: comprar y mantener")

    df = df[start_date:end_date]

    BH_Strategy =  BuyAndHoldStrategy
    BH_Cerebro, initial_value, final_value, ta, dd, ma = execute_strategy(BH_Strategy, df, commission)

    # Save results
    execution_analysis.printAnalysis('comprar_y_mantener', data_name, initial_value, final_value, ta, dd, ma)
    # Save simulation chart
    execution_plot.plot_simulation(BH_Cerebro, 'comprar_y_mantener', data_name, start_date, end_date)

    return BH_Cerebro, BH_Strategy


def execute_classic_strategy(df, commission, data_name, start_date, end_date):

    print_execution_name("Estrategia: clásica")

    df = df[start_date:end_date]

    Classic_Strategy =  ClassicStrategy
    Classic_Cerebro, initial_value, final_value, ta, dd, ma = execute_strategy(Classic_Strategy, df, commission)

    # Save results
    execution_analysis.printAnalysis('estrategia_clasica', data_name, initial_value, final_value, ta, dd, ma)
    # Save simulation chart
    execution_plot.plot_simulation(Classic_Cerebro, 'estrategia_clasica', data_name, start_date, end_date)

    return Classic_Cerebro, Classic_Strategy


def execute_neural_network_strategy(df, options, comm, data_name, s_test, e_test):

    print_execution_name("Estrategia: red neuronal")

    # ------------ Get parameters ------------#
    gain = options['gain']
    loss = options['loss']
    n_day = options['n_day']
    epochs = options['epochs']

    s_test_date = datetime.strptime(s_test, '%Y-%m-%d')
    s_train = s_test_date.replace(year = s_test_date.year - 2)
    e_train = s_test_date - timedelta(days=1)

    # ------------ Preprocess dataset ------------ #

    df = func_utils.add_features(df)
    df = func_utils.add_label(df, gain = gain, loss = loss, n_day = n_day, commission = comm)

    # ------------ Split train and test ------------ #

    df_train, df_test, X_train, X_test, y_train, y_test = func_utils.split_df_date(df, s_train, e_train, s_test, e_test)

    # ------------ Normalization ------------ #

    print("Normalizando datos...")
    sc = StandardScaler()
    X_train = sc.fit_transform(X_train)
    X_test = sc.fit_transform (X_test)

    # Transform data in a correct format to use in Keras
    X_train = np.reshape(X_train, (X_train.shape[0], X_train.shape[1], 1))
    X_test = np.reshape(X_test, (X_test.shape[0], X_test.shape[1], 1))

    # ------------ Get prediction model ------------ #

    print("Entrenando red neuronal...")

    neural_network = model.NeuralNetwork()
    neural_network.build_model(input_shape = (X_train.shape[1], 1))
    neural_network.train(X_train, y_train, epochs = epochs)

    # ------------ Get accuraccy ------------ #

    train_accuracy = neural_network.get_accuracy(X_train, y_train)
    test_accuracy = neural_network.get_accuracy(X_test, y_test)

    print("\nRESULTADOS PREDICCION:\n")
    print("TRAIN :: Porcentaje de acierto: " + str(train_accuracy))
    print("TEST  :: Porcentaje de acierto: " + str(test_accuracy))

    # ------------------------ Backtesting ------------------------ #

    # Initialize neural network memory
    neural_network.init_memory(X_train[len(X_train)-15:len(X_train)], y_train[len(y_train)-15:len(y_train)])

    # Create an instance from NeuralNetworkStrategy class and assign parameters
    NN_Strategy = NeuralNetworkStrategy
    NN_Strategy.X_test = X_test
    NN_Strategy.y_test = y_test
    NN_Strategy.model = neural_network
    NN_Strategy.n_day = n_day

    # Execute strategy
    NN_Cerebro, initial_value, final_value, ta, dd, ma = execute_strategy(NN_Strategy, df_test, comm)
    # Save results
    execution_analysis.printAnalysis('red_neuronal', data_name, initial_value, final_value, ta, dd, ma, train_accuracy, test_accuracy)
    # Save simulation chart
    execution_plot.plot_simulation(NN_Cerebro, 'red_neuronal', data_name, s_test, e_test)

    return NN_Cerebro, NN_Strategy


def execute_pso_strategy(df, commission, data_name, s_test, e_test):

    print_execution_name("Estrategia: particle swar optimization")

    # ------------ Obtenemos los conjuntos de train y test ------------ #

    s_test_date = datetime.strptime(s_test, '%Y-%m-%d')
    s_train = s_test_date.replace(year = s_test_date.year - 2)
    e_train = s_test_date - timedelta(days=1)

    gen_representation = geneticRepresentation.GeneticRepresentation(df, s_train, e_train, s_test, e_test)

    # ------------ Fijamos hiperparámetros ------------ #

    n_particles=20
    dimensions=107
    options = {'c1': 0.5, 'c2': 0.3, 'w':0.9}
    max_bound = 1.0 * np.ones(dimensions-2)
    min_bound = -max_bound
    max_bound = np.append(max_bound, [1.0, 0.0])
    min_bound = np.append(min_bound, [0.0, -1.0])
    bounds = (min_bound, max_bound)
    iters = 100

    # Call instance of PSO
    optimizer = ps.single.GlobalBestPSO(n_particles=n_particles, dimensions=dimensions, options=options, bounds=bounds)

    # Perform optimization
    kwargs={'from_date': s_train, 'to_date': e_train}
    best_cost, best_pos = optimizer.optimize(gen_representation.cost_function, iters=iters, **kwargs)

    # Create an instance from CombinedSignalStrategy class and assign parameters
    PSO_Strategy = CombinedSignalStrategy
    w, buy_threshold, sell_threshold = func_utils.get_split_w_threshold(best_pos)
    PSO_Strategy.w = w
    PSO_Strategy.buy_threshold = buy_threshold
    PSO_Strategy.sell_threshold = sell_threshold
    PSO_Strategy.period_list = gen_representation.period_list
    PSO_Strategy.moving_average_rules = gen_representation.moving_average_rules
    PSO_Strategy.moving_averages = gen_representation.moving_averages_test
    PSO_Strategy.optimizer = optimizer
    PSO_Strategy.gen_representation = gen_representation

    df_test = gen_representation.df_test
    df_train = gen_representation.df_train

    PSO_Cerebro, initial_value, final_value, ta, dd, ma = execute_strategy(PSO_Strategy, df_test, commission)

    # Guardamos los resultados
    execution_analysis.printAnalysis('particle_swarm_optimization', data_name, initial_value, final_value, ta, dd, ma)
    # Guardamos la grafica de la simulacion
    execution_plot.plot_simulation(PSO_Cerebro, 'particle_swarm_optimization', data_name, s_test, e_test)

    return PSO_Cerebro, PSO_Strategy