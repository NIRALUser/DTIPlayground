

from dtiprep.modules import DTIPrepModule


class BASELINE_Average(DTIPrepModule):
    def __init__(self,*args,**kwargs):
        super().__init__(BASELINE_Average)

    def process(self):
        super().process()
        print("Child method begins")
