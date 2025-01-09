from baidu_share import BaiDuPan

bd = BaiDuPan()
#print(bd.verifyCookie())
#print(bd.getFileList('/apps/bypy'))
print(bd.saveShare("https://pan.baidu.com/s/1bIWtZ6qhMhmz2mBa26DKqA", "yhmj", '/apps/bypy/'))