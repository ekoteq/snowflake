from time import time
import random

# returns a random integer that is no less than one, and no greater
# than the maximum integer value of the bits provided
def generate_seed(bits):
    return random.randint(1, (2^bits-1))

class Pyflake():
    def __init__(self, epoch, timestamp, pid, seed, sequence):
        self.epoch = epoch
        self.pid = pid
        self.seed = seed
        self.timestamp = timestamp
        self.sequence = sequence

    def timestamp_bits(self):
        return (self.timestamp - self.epoch).bit_length()

    def pid_bits(self):
        return self.pid.bit_length()

    def seed_bits(self):
        return self.seed.bit_length()

    def sequence_bits(self):
        return self.sequence.bit_length()

    def pid_shift(self):
        return self.sequence_bits()

    def seed_shift(self):
        return self.pid_shift() + self.pid_bits()

    def timestamp_shift(self):
        # left-hand bit position where the timestamp can be found
        return self.seed_shift() + self.seed_bits()

    # generating the snowflake via a local method
    # allows clients (albeit a bit dangerously)
    # to modify the snowflake by modifying related attribute
    # values
    def snowflake(self):
        return (
            # subtract the current timestamp from the defined epoch, which
            # returns the miliseconds passed since the epoch time, and define
            # the timestamp value in the sequence relative to the defined
            # 'timestamp_shift' bit value defined above
            ((self.timestamp-self.epoch) << self.timestamp_shift) |
            # the same is done to the seed and pid values for sequence placement
            (self.seed << self.seed_shift) |
            (self.pid << self.pid_shift) |
            # finally, the current sequence value is returned, preventing race
            # conditions and ensuring uniqueness across IDs generated within
            # the same millisecond
            self.sequence
        )
# returns a pyflake_generator that allows a client to generate IDs by calling
# `next(<pyflake_generator>)` on the generator
def pyflake_generator(epoch, pid, seed, sequence_bits, sleep = lambda x: time.sleep(x / 1000)):

    # local pyflake_generator variables
    last_timestamp = -1
    sequence = 0
    sequence_mask = -1 ^ (-1 << sequence_bits)

    # this process will loop 'while true' until a yield statement is
    # reached, at which time the loop will be paused pending a call to
    # `next(<generator>)`, which will return a string value and increment
    # the sequence. Multiple unique IDs may be crafted from a single
    # pyflake_generator instance, and near-infinite unique IDs may be
    # generated by utilizing multiple pyflake_generator instances
    while True:
        timestamp = int(time() * 1000)

        # If the previous timestamp is greater than the current timestamp,
        # as if time is moving backwards, wait until time catches up to
        # ensure only sequential IDs are issued in ascending order
        if last_timestamp > timestamp:
            sleep(last_timestamp-timestamp)
            continue

        # if an ID was already generated under the current sequence value
        # as such may be the case in race conditions, where multiple IDs
        # are requested at the same time, we want to increase the sequence
        # before proceeding.
        if last_timestamp == timestamp:
            sequence = (sequence + 1) & sequence_mask
            # in the event the sequence becomes overrun, the sequence is updated
            # and the process continues after a one millisecond delay, ensuring a new
            # timestamp is used, preventing conflicts in IDs where sequences are
            # full, or cannot provide further unique values
            if sequence == 0:
                sequence = -1 & sequence_mask
                sleep(1)
                continue
        # Otherwise, if the current timestamp is greater than the
        # previous timestamp, the sequence is reset, as there will be no
        # conflicts with previous IDs under a new timestamp
        else:
            sequence = 0

        # update the 'last_timestamp' value with the most-recently obtained
        # timestamp, used to generate the currently-requested snowflake
        last_timestamp = timestamp

        # yield the loop and return the value to the requesting client
        # pending future client requests
        yield Pyflake(
            epoch = epoch,
            timestamp = timestamp,
            pid = pid,
            seed = seed,
            sequence = sequence
        )

# a snowflake pyflake_generator client class
# use of this class is not required - a pyflake_generator may be created by
# calling the global `pyflake_generator` function above
# the below class just makes managing the generator that much easier
class PyflakeClient():
    def __init__(self, epoch):
        # the client relies on this to translate snowflake IDs back into
        # timestamps - changing this value will not affect the available
        # generator
        self.epoch = epoch
        # general information - how many snowflakes have been generated
        # since client initialization, indiscriminate of generator renewals
        self._generated = 0
        # a cache of snowflakes generated since initialization
        self._cache = dict()

    # quickly ensure that generated snowflake attributes are valid
    # and will properly construct if passed to a `Pyflake` class
    def validate(self, epoch, timestamp, pid, seed, sequence):
        # snowflakes are <=64 bits!
        assert 0 < ( timestamp.bit_length() + pid.bit_length() + seed.bit_length() + sequence.bit_length() ) <= 64

    # general information about the client instance
    def get_info(self):
        res = {
            'epoch': self.epoch,
            'pid': getattr(self, 'pid', None),
            'seed': getattr(self, 'seed', None),
            'generated': self._generated,
        }
        # checks if the client has a generator available
        # and adds the relevant status to the response
        if getattr(self, 'generator', None):
            res['generator'] = True
        else:
            res['generator'] = False

        return res

    # destroys the current pyflake_generator, if one exists
    def destroy_generator(self):
        # we only delete the attribute if it exists
        if getattr(self, 'generator', None):
            delattr(self, 'pid')
            delattr(self, 'seed')
            delattr(self, 'generator')
        else:
            raise AttributeError(f'Cannot destroy generator: No generator is available to destroy.')

    # creates a new pyflake_generator, if one does not exist
    def create_generator(self, pid, seed):
        # requesting clients will need to ensure existing generators are destroyed
        # before trying to create a new one

        # if the requesting client needs more than one generator, more than one
        # client instance should be created, since snowflakes are unique to the
        # pid and seed used to generate them, and especially unique to the client's
        # epoch timestamp.
        if not getattr(self, 'generator', None):
            # changing the values of these attributes will not affect the generator
            # so there's no need to discourage clients from changing their values
            setattr(self, 'pid', pid)
            setattr(self, 'seed', seed)

            # the generator can be re-constructed via the `create_generator` method
            # and it's up to the requesting client to manage its creation or destruction
            # so there's no need to discourage modifying the attribute
            setattr(self, 'generator', pyflake_generator(self.epoch, pid, seed))
        else:
            raise AttributeError(f'Cannot create generator: Generator already exists for use.')

    # replaces the current pyflake_generator with a new one, and allows
    # the requesting client to define a process ID and seed value
    def renew_generator(self, pid, seed):
        try:
            self.destroy_generator()
        except Exception as e:
            # the only acceptable exception is an `AttributeError`
            # which indicates a generator is not currently available
            # so one could easily be created in its place
            # in this case, we don't want to raise the exception
            if isinstance(e, AttributeError):
                self.create_generator(pid, seed)
            else:
                # otherwise, raise the exception
                raise e
        else:
            # if the destroy 
            self.create_generator(pid, seed)

    # shortcut function, quickly returns a snowflake ID from the attached
    # pyflake_generator, based on timestamp value at the time the request
    # was made
    def generate(self):
        # a deconstructed snowflake reference object
        # direct access to the snowflake ID is available via `res.snowflake`
        # or `res.string()`
        res = next(self.generator)

        # add the entry to the cache
        self._cache.update([(res.snowflake(), res)])

        # increase the number of generated records
        self._generated += 1

        # finally, return the class object requesting client
        return res

    # all generated IDs may be converted back into a timestamp by stripping
    # the lower 22 bits and adding the epoch time into the remaining value.
    # A timestamp cannot be returned without knowing the epoch used to
    # generate it.
    def timestamp(self, snowflake, fmt = 'ms'):
        # strip the lower 22 bits holding the pid, seed, and sequence
        timestamp = snowflake >> 22
        # adjust for defined epoch time (ms)
        timestamp += self.epoch

        # clients can optionally request timestamp in seconds format
        # by specifying fmt as 's' instead of 'ms'
        # clients may quickly convert values between `float` and
        # `int` once returned, but should expect to receive a `float`
        # type response from this method, even if `seconds` format
        # isn't requested
        if fmt == 's':
            timestamp = timestamp / 1000

        return timestamp