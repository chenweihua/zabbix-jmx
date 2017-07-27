#!/usr/bin/env python
#coding=utf-8
'''
##
## 功能: 调用jmxclient.jar获取JMX的各项指标
## 说明: 用于zabbix自动发现告警
##
'''

import sys
import os
import commands
import subprocess
import json
#import argparse
import socket
import threading

java = commands.getoutput("which java")
jmxclient = "/etc/zabbix/script/jmxmonitor.jar"
jvmport_cmd = "ps aux|grep -oP '(?<=jmxremote.port=)[0-9]+'"
#jvmpw_cmd = "ps aux|grep -oP '(?<=jmxremote.authenticate=)(true|false)'"

hostname = socket.gethostname()
zbx_sender='/usr/local/bin/zabbix_sender'
zbx_cfg='/etc/zabbix/zabbix_agentd.conf'
zbx_tmp_file='/tmp/.zabbix_jmx_status'

jvmkey_dict = [
                   "java.lang:type=Threading DaemonThreadCount",
                   "java.lang:type=Threading ThreadCount",
                   "java.lang:type=Runtime Uptime",
                   "java.lang:type=GarbageCollector,name=PS Scavenge CollectionTime",
                   "java.lang:type=GarbageCollector,name=PS MarkSweep CollectionTime",
                   "java.lang:type=GarbageCollector,name=ConcurrentMarkSweep CollectionTime",
                   "java.lang:type=GarbageCollector,name=ParNew CollectionTime",
                   "java.lang:type=GarbageCollector,name=PS MarkSweep CollectionCount",
                   "java.lang:type=GarbageCollector,name=PS Scavenge CollectionCount",
                   "java.lang:type=GarbageCollector,name=ConcurrentMarkSweep CollectionCount",
                   "java.lang:type=GarbageCollector,name=ParNew CollectionCount",
                   "java.lang:type=OperatingSystem OpenFileDescriptorCount",
                   "java.lang:type=OperatingSystem MaxFileDescriptorCount",
                   "java.lang:type=Memory HeapMemoryUsage",
                   "java.lang:type=ClassLoading UnloadedClassCount",
                   "java.lang:type=ClassLoading LoadedClassCount",
                ]

jmx_threads = []

def get_jvmcmd(jport):
    jvm_command = "%s -jar %s  127.0.0.1:%s" % (java,jmxclient,jport)
    #print jvm_command
    return jvm_command

def get_jmx(jport):
    '''
      调用jmxclient.jar获取Java的性能指标
    '''
    jvmcmd = get_jvmcmd(jport)
    output = subprocess.Popen(jvmcmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    data = output.stdout.readlines()
    #print data
    data_dict = dict((l.strip().split('$') for l in data ))

    for jmxkey in [key for key in jvmkey_dict if key in data_dict.keys()]:
        if "Memory HeapMemoryUsage" in jmxkey:
            heapmem_str = data_dict[jmxkey].replace("(","").replace(")","").replace(";","")
            Heapmem_dict = dict([item.split('=') for item in heapmem_str.split()])
            for (heapmem_key,heapmem_value) in  Heapmem_dict.items():
                customkey = jmxkey.replace("java.lang:type=","").replace("name=",".").replace(",","").replace(" ",".")
                zbx_data = "%s jmx.status[%s,%s.%s] %s" %(hostname,jport,customkey,heapmem_key,heapmem_value)
                with open(zbx_tmp_file,'a') as file_obj: file_obj.write(zbx_data + '\n')
        else:
            customkey = jmxkey.replace("java.lang:type=","").replace("name=",".").replace(",","").replace(" ",".")
            zbx_data = "%s jmx.status[%s,%s] %s" %(hostname,jport,customkey,data_dict[jmxkey])
            with open(zbx_tmp_file,'a') as file_obj: file_obj.write(zbx_data + '\n')

def jvm_port_discovery():
    output = subprocess.Popen(jvmport_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    jvm_port_list = output.stdout.readlines()
    return jvm_port_list

def file_truncate():
    '''
      用于清空zabbix_sender使用的临时文件
    '''
    with open(zbx_tmp_file,'w') as fn: fn.truncate()

def zbx_tmp_file_create():
    '''
      创建zabbix_sender发送的文件内容
    '''
    jvmport_list = jvm_port_discovery()
    for jvmport_tmp in jvmport_list:
        jvmport = jvmport_tmp.strip('\n')
#        get_jmx(jvmport)
        th = threading.Thread(target=get_jmx,args=(jvmport,))
        th.start()
        jmx_threads.append(th)

def send_data_zabbix():
    '''
      调用zabbix_sender命令，将收集的key和value发送至zabbix server
    '''
    zbx_tmp_file_create()
    for get_jmxdata in jmx_threads:
        get_jmxdata.join()
    zbx_sender_cmd = "%s -c %s -i %s" %(zbx_sender,zbx_cfg,zbx_tmp_file)
    zbx_sender_status,zbx_sender_result = commands.getstatusoutput(zbx_sender_cmd)
    file_truncate()
    print zbx_sender_status

def zbx_discovery():
    '''
      用于zabbix自动发现JVM端口
    '''
    jvm_zabbix = []
    jvmport_list = jvm_port_discovery()
    for jvmport_tmp in jvmport_list:
        jvmport = jvmport_tmp.strip('\n')
        jvm_zabbix.append({'{#JVMPORT}' : jvmport,
                         })
    return json.dumps({'data': jvm_zabbix}, sort_keys=True, indent=7,separators=(',', ':'))

def cmd_line_opts(arg=None):
    class ParseHelpFormat(argparse.HelpFormatter):
        def __init__(self, prog, indent_increment=5, max_help_position=50, width=200):
            super(ParseHelpFormat, self).__init__(prog, indent_increment, max_help_position, width)

    parse = argparse.ArgumentParser(description='Jmx监控"',
                                    formatter_class=ParseHelpFormat)
    parse.add_argument('--version', '-v', action='version', version="0.1", help='查看版本')
    parse.add_argument('--discovery-jvmport', action='store_true', help='获取JVM端口')
    parse.add_argument('--send-jmx-data', action='store_true', help='发送JMX指标数据至zabbix')

    if arg:
        return parse.parse_args(arg)
    if not sys.argv[1:]:
        return parse.parse_args(['-h'])
    else:
        return parse.parse_args()


if __name__ == '__main__':
    #opts = cmd_line_opts()
    ar = sys.argv[1]
    #print ar
    if ar == 'jvm_disc':
        print zbx_discovery()
    elif ar == 'send_data':
        send_data_zabbix()
    #else:
    #    cmd_line_opts(arg=['-h'])
