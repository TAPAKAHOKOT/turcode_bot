import time


class Logger:
    tg = None

    @staticmethod
    def log(log_type: str, *args):
        print(f'{log_type} {int(time.time())}:', *args)

    def info(self, *args):
        self.log('INFO', *args)

    def error(self, *args):
        self.log('ERROR', *args)

        # if self.tg is not None:
        #     self.tg.notify_admins('ERROR', *args)
