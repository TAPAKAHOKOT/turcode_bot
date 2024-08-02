import time


class Logger:
    # LOGGING
    def log(self, type, *args):
        print(f'{type} {int(time.time())}:', *args)

    def info(self, *args):
        self.log('INFO', *args)

    def error(self, *args):
        self.log('ERROR', *args)
        notify_admins('ERROR', *args)
