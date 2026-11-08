#!/usr/bin/env python3
"""Compile real settings/protocol/calibration C with simulated GPIO and EEPROM.

Requires host GCC/Clang. No keyboard access, flashing, or QMK shared edits.
"""
from pathlib import Path
import argparse,subprocess,tempfile
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('qmk_root',type=Path)
ROOT=parser.parse_args().qmk_root.resolve()
BOARD=ROOT/'keyboards/xwhatsit'
QUANTUM=r'''
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
#define MATRIX_ROWS 8
#define MATRIX_COLS 16
#define CONTROLLER_IS_UNIVERSAL_MODEL_F 1
#define RAW_EPSIZE 32
#define E2END 1023
#define KC_NO 0
#define PROGMEM
#define memcpy_P memcpy
#define strlen_P strlen
#define wait_ms(x) ((void)(x))
typedef uint16_t matrix_row_t;
uint16_t matrix_get_row(uint8_t row);
uint16_t keycode_at_keymap_location_raw(uint8_t layer,uint8_t row,uint8_t col);
void bootloader_jump(void);
'''
HARNESS=r'''
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include "quantum.h"
#include "capsense.h"
#include "calibration_config.h"
#include "util_comm.h"
uint8_t memory[1024]; int budget=-1,writes=0,booted=0,measure_calls=0,cal_calls=0;
jmp_buf power_loss;
bool keyboard_scan_enabled=true;
matrix_row_t held[MATRIX_ROWS];
uint16_t cal_thresholds[CAPSENSE_CAL_BINS],cal_tr_allzero,cal_tr_allone;
matrix_row_t assigned_to_threshold[CAPSENSE_CAL_BINS][MATRIX_CAPSENSE_ROWS];
void raw_hid_receive_kb(uint8_t*,uint8_t);
uint16_t matrix_get_row(uint8_t row){return held[row];}
void matrix_scan_raw(matrix_row_t *result){memcpy(result,held,sizeof(held));}
uint16_t keycode_at_keymap_location_raw(uint8_t l,uint8_t r,uint8_t c){return r<2&&c<4;}
void bootloader_jump(void){booted++;}
uint8_t eeprom_read_byte(const uint8_t*p){return memory[(uintptr_t)p];}
void eeprom_update_byte(uint8_t*p,uint8_t v){
 assert((uintptr_t)p<sizeof(memory));
 if(budget==0)longjmp(power_loss,1);
 if(budget>0)budget--;
 if(memory[(uintptr_t)p]!=v){memory[(uintptr_t)p]=v;writes++;}
}
void eeprom_read_block(void*d,const void*s,size_t n){memcpy(d,memory+(uintptr_t)s,n);}
void eeprom_update_block(const void*s,void*d,size_t n){for(size_t i=0;i<n;i++)eeprom_update_byte((uint8_t*)d+i,((uint8_t*)s)[i]);}
uint16_t measure_middle(uint8_t col,uint8_t row,uint8_t time,uint8_t reps){return 100+col*10+row;}
uint16_t calibration_measure_all_valid_keys(uint8_t time,uint8_t reps,bool zero){return zero?200:10;}
uint16_t measure_middle_keymap_coords(uint8_t c,uint8_t r,uint8_t t,uint8_t reps){measure_calls++;return 200;}
CALIBRATION_SOURCE
void calibration(void){cal_calls++;model_calibration();}
struct packet{uint8_t before[8],data[32],after[8];} packet;
void send(uint8_t op,const uint8_t*record){
 memset(&packet,0x5a,sizeof(packet));memset(packet.data,0,32);
 packet.data[0]=0x55;packet.data[1]=0xaa;packet.data[2]=op;
 if(record)memcpy(packet.data+3,record,8);
 raw_hid_receive_kb(packet.data,32);
 for(int i=0;i<8;i++){assert(packet.before[i]==0x5a);assert(packet.after[i]==0x5a);}
}
int main(void){
 memset(memory,0xff,sizeof(memory));xcal_load();assert(xcal_valid(xcal_settings));
 uint8_t defaults[8],candidate[8],old[8];memcpy(defaults,xcal_settings,8);
 for(int byte=0;byte<8;byte++)for(int bit=0;bit<8;bit++){
  memcpy(candidate,defaults,8);candidate[byte]^=1<<bit;assert(!xcal_valid(candidate));
 }
 for(int field=1;field<=4;field++)for(int value=0;value<256;value++){
  memcpy(candidate,defaults,8);candidate[field]=value;candidate[7]=xcal_crc(candidate);
  bool expected=field<3?(value>=1&&value<=32):field==3?((value&15)<=5&&(value>>4)<=5):(value>=1&&value<=CAPSENSE_CAL_BINS);
  assert(!!xcal_valid(candidate)==expected);
 }
 memcpy(candidate,defaults,8);candidate[1]=10;candidate[2]=6;candidate[3]=0x55;candidate[4]=3;candidate[5]=120;candidate[6]=0;candidate[7]=xcal_crc(candidate);
 memcpy(xcal_settings,defaults,8);xcal_settings[1]=9;xcal_settings[7]=xcal_crc(xcal_settings);xcal_save();memcpy(old,memory+15,8);
 for(int cutoff=0;cutoff<11;cutoff++){
  memcpy(memory+15,old,8);memcpy(xcal_settings,candidate,8);budget=cutoff;
  if(!setjmp(power_loss))xcal_save();budget=-1;xcal_load();
  assert(!memcmp(xcal_settings,defaults,8)||!memcmp(xcal_settings,candidate,8)||!memcmp(xcal_settings,old,8));
 }
 memcpy(xcal_settings,defaults,8);
 send(UTIL_COMM_GET_VERSION,NULL);assert(packet.data[2]==0x22&&packet.data[4]==1);
 send(UTIL_COMM_CAL_CAPS,NULL);assert(!memcmp(packet.data+3,"XCAL",4));
 int before=cal_calls;held[0]=1;send(UTIL_COMM_CAL_APPLY_SAVE,candidate);assert(packet.data[2]==0x24&&cal_calls==before&&!memcmp(xcal_settings,defaults,8));held[0]=0;
 uint8_t bad[8];memcpy(bad,candidate,8);bad[7]^=1;send(UTIL_COMM_CAL_APPLY_SAVE,bad);assert(packet.data[2]==0x23&&cal_calls==before);
 memset(assigned_to_threshold,0xff,sizeof(assigned_to_threshold));send(UTIL_COMM_CAL_APPLY_SAVE,candidate);
 assert(packet.data[2]==0x22&&cal_calls==before+1&&!memcmp(memory+15,candidate,8));
 for(int row=0;row<MATRIX_CAPSENSE_ROWS;row++)for(int col=0;col<MATRIX_COLS;col++){
  int assignments=0;for(int bin=0;bin<CAPSENSE_CAL_BINS;bin++)assignments+=!!(assigned_to_threshold[bin][row]&(1<<col));
  assert(assignments==(row<2&&col<4));
 }
 for(int count=0;count<256;count++){
  memset(&packet,0x5a,sizeof(packet));memset(packet.data,0,32);packet.data[0]=0x55;packet.data[1]=0xaa;packet.data[2]=UTIL_COMM_GET_SIGNAL_VALUE;packet.data[5]=count;
  raw_hid_receive_kb(packet.data,32);assert(packet.data[2]==(count>=1&&count<=14?0x22:0x23));
  for(int i=0;i<8;i++)assert(packet.after[i]==0x5a);
 }
 uint8_t invalid_bin[8]={255};send(UTIL_COMM_GET_THRESHOLDS,invalid_bin);assert(packet.data[2]==0x23);
 memset(memory,0x66,sizeof(memory));held[0]=1;send(UTIL_COMM_CAL_DEFAULTS,NULL);held[0]=0;assert(packet.data[2]==0x22&&!memcmp(memory+15,defaults,8));assert(memory[14]==0x66&&memory[23]==0x66);
 send(UTIL_COMM_ENTER_BOOTLOADER,NULL);assert(booted==1&&!keyboard_scan_enabled);
 send(UTIL_COMM_ERASE_EEPROM,NULL);for(int i=0;i<1024;i++)assert(memory[i]==255);
 xcal_load();assert(!memcmp(xcal_settings,defaults,8));
 puts("PASS: settings CRC/ranges, every interrupted commit, held-key rejection, real calibration reassignment, protocol bounds, defaults, EEPROM erase and boot entry");
}
'''
with tempfile.TemporaryDirectory(prefix='xwhatsit-native-') as folder:
 temp=Path(folder)
 (temp/'quantum.h').write_text(QUANTUM)
 (temp/'raw_hid.h').write_text('#pragma once\n')
 (temp/'progmem.h').write_text('#pragma once\n#include "quantum.h"\n')
 (temp/'eeprom.h').write_text('#pragma once\n#include <stdint.h>\n#include <stddef.h>\nuint8_t eeprom_read_byte(const uint8_t*);\nvoid eeprom_update_byte(uint8_t*,uint8_t);\nvoid eeprom_read_block(void*,const void*,size_t);\nvoid eeprom_update_block(const void*,void*,size_t);\n')
 internal=temp/'quantum/nvm/eeprom/nvm_eeprom_eeconfig_internal.h';internal.parent.mkdir(parents=True)
 internal.write_text('#pragma once\n#define EECONFIG_KB_DATA_SIZE 0\n#define EECONFIG_USER_DATA_SIZE 0\n#define EECONFIG_KEYBOARD ((uint32_t*)15)\n#define EECONFIG_USER ((uint32_t*)19)\n')
 source=(BOARD/'matrix.c').read_text();calibration=source[source.index('void calibration(void)'):source.index('\nvoid set_leds(')].replace('void calibration(void)','static void model_calibration(void)',1)
 (temp/'harness.c').write_text(HARNESS.replace('CALIBRATION_SOURCE',calibration))
 command=['gcc','-std=gnu11','-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-DXWHATSIT_RUNTIME_CALIBRATION','-I'+str(temp),'-I'+str(BOARD),str(temp/'harness.c'),str(BOARD/'calibration_config.c'),str(BOARD/'util_comm.c'),'-o',str(temp/'test')]
 subprocess.run(command,check=True)
 subprocess.run([str(temp/'test')],check=True)
