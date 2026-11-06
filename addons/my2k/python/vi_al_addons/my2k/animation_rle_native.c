/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Exact bounded PackBits encoder for opaque RGB565 pairs. Stored CRS data is
 * unchanged. Python remains the fallback and independent format oracle. */
#include <stddef.h>
#include <stdint.h>
#if defined(_WIN32)
#define RLE_EXPORT __declspec(dllexport)
#else
#define RLE_EXPORT
#endif
static int equal(const uint8_t *p,size_t a,size_t b){return p[2*a]==p[2*b]&&p[2*a+1]==p[2*b+1];}
RLE_EXPORT size_t my2k_rle565_encode(const uint8_t *raw,size_t n,uint8_t *out,size_t capacity){
 if(!raw||!out||!n||(n&1u)||n>4096u||capacity<n+(n+255u)/256u)return 0;
 size_t i=0,wrote=0,count=n/2;
 while(i<count){
  size_t run=1;while(run<128&&i+run<count&&equal(raw,i+run,i))run++;
  if(run>=3){out[wrote++]=(uint8_t)(128|(run-1));out[wrote++]=raw[2*i];out[wrote++]=raw[2*i+1];i+=run;continue;}
  size_t start=i;i+=run;
  while(i<count&&i-start<128){
   run=1;while(run<3&&i+run<count&&equal(raw,i+run,i))run++;
   if(run>=3)break;
   size_t available=128-(i-start);i+=run<available?run:available;
  }
  out[wrote++]=(uint8_t)(i-start-1);size_t bytes=(i-start)*2;for(size_t j=0;j<bytes;++j)out[wrote+j]=raw[start*2+j];wrote+=bytes;
 }
 return wrote;
}

#if defined(_WIN32)
/* This helper has no runtime state, CRT dependencies or initialization work. */
int DllMain(void *module, unsigned reason, void *reserved) {
 (void)module; (void)reason; (void)reserved;
 return 1;
}
#endif
