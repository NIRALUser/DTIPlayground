from PyQt5.QtWidgets import * 
from PyQt5 import QtCore, QtGui

class LoadingButton(QPushButton):
  @QtCore.pyqtSlot()
  def start(self):
    if hasattr(self, "_movie"):
      self._movie.start()

  @QtCore.pyqtSlot()
  def stop(self):
    if hasattr(self, "_movie"):
      self._movie.stop()
      self.setIcon(QtGui.QIcon())

  def setGif(self, filename):
    if not hasattr(self, "_movie"):
      self._movie = QtGui.QMovie(self)
      self._movie.setFileName(filename)
      self._movie.frameChanged.connect(self.on_frameChanged)
      if self._movie.loopCount() != -1:
        self._movie.finished.connect(self.start)
    self.stop()

  @QtCore.pyqtSlot(int)
  def on_frameChanged(self, frameNumber):
    self.setIcon(QtGui.QIcon(self._movie.currentPixmap()))
