"""Counted work shared by terminal and dashboard progress displays."""
from tqdm import tqdm as TerminalProgress


class Progress:
    def __init__(self, iterable=None, *, callback=None, **options):
        self.iterable = iterable
        self.callback = callback
        self.done = 0
        self.total = options.get("total", len(iterable) if iterable is not None else None)
        self.stage = options.get("desc", "Working")
        self.unit = options.get("unit", "items")
        self.terminal = TerminalProgress(total=self.total, **{k: v for k, v in options.items() if k != "total"})
        self.report()

    def report(self):
        if self.callback:
            self.callback(self.stage, self.done, self.total, self.unit)

    def update(self, count=1):
        self.done += count
        self.terminal.update(count)
        self.report()

    def close(self):
        self.terminal.close()

    def __iter__(self):
        try:
            for item in self.iterable:
                yield item
                self.update()
        finally:
            self.close()
