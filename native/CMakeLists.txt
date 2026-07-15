cmake_minimum_required(VERSION 3.20)
project(neuroswarm_native C)

add_library(neuroswarm_native OBJECT json_sve2.c mte_kv.c)

