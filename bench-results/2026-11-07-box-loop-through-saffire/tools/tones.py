import numpy as np
def rd24(p):
    b=np.frombuffer(open(p,"rb").read(),np.uint8); b=b[:len(b)//6*6].reshape(-1,3)
    v=(b[:,0].astype(np.int32)|b[:,1].astype(np.int32)<<8|b[:,2].astype(np.int32)<<16); v=np.where(v&0x800000,v-0x1000000,v)/8388608.0
    return v.reshape(-1,2)
def rd16(p):
    v=np.frombuffer(open(p,"rb").read(),"<i2"); return (v[:len(v)//2*2]/32768.0).reshape(-1,2)
for name,x in (("piv records pedal OUT (Saffire in 1,2)",rd24("/tmp/piv-in.raw")),("vip records pedal IN (codec L,R)",rd16("/tmp/vip-in.raw"))):
    seg=x[48000:48000*5]
    for c in range(2):
        y=seg[:,c]; S=np.abs(np.fft.rfft(y*np.hanning(len(y))))**2; f=np.fft.rfftfreq(len(y),1/48000)
        b=lambda fq:10*np.log10(S[(f>fq-5)&(f<fq+5)].sum()/S.sum()+1e-20)
        print(f"{name} ch{c+1}: rms {20*np.log10(np.sqrt(np.mean(y**2))+1e-12):.1f} dBFS, peak {20*np.log10(np.max(np.abs(y))+1e-12):.1f}, 440Hz share {b(440):.1f} dB, 1kHz share {b(1000):.1f} dB, 50Hz share {b(50):.1f} dB")
