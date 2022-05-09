from PyQt5.QtCore import QObject
from PyQt5.QtCore import pyqtSignal as Signal


class ModulesDetailsCommunicate(QObject):

  update_params = Signal()
  send_params = Signal(list)
  call_update_user_preferences_file = Signal(dict)


  def __init__(self):
    super(ModulesDetailsCommunicate, self).__init__()

  def modif(self):
    self.update_params.emit()

  def SendParams(self, params):
    self.send_params.emit(params)

  def CallUpdateUserPreferencesFile(self, new_preferences):
    self.call_update_user_preferences_file.emit(new_preferences)

    
