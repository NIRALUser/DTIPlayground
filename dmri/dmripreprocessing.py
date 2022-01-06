from dmri import DTIPlayground
import dmri.common as common
import dmri.common.tools as tools

logger=common.logger.write

class DMRIPreprocessing(DTIPlayground):
  def __init__(*args,**kwargs):
    pass

  def initialize(self):
    logger("initialize");
    
  def preprocess(self):
    logger("Preprocessing")

  def process(self):
    logger("Processing")

  def postprocess(self):
    logger("Postprocessing")

