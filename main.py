import sys
import time
import math
import random

# all generated IDs may be converted back into a timestamp by stripping
# the lower 22 bits and adding the epoch time into the remaining value.
# A timestamp cannot be returned without knowing the epoch used to
# generate it.
def to_timestamp(epoch, id, fmt = 'ms'):
    id = id >> 22   # strip the lower 22 bits holding the pid, seed, and sequence
    id += epoch # adjust for defined epoch time (ms)

    # clients can optionally request timestamp in seconds format
    # by specifying fmt as 's' instead of 'ms'
    # this may return a float value
    if fmt == 's':
        id = id / 1000

    return id

# returns a random integer that is no less than one, and no greater
# than the maximum integer value of the bits provided
def generate_seed(bits):
    return random.randint(1, (2^bits-1))

# returns a pyflake_generator that allows a client to generate IDs by calling
# `next(<pyflake_generator>)` on the generator
def pyflake_generator(epoch, pid, seed, sleep = lambda x: time.sleep(x / 1000)):
    # A snowflake is comprised of 64 total bits
    # 42 of the 64 bits exist in the timestamp value (in milliseconds)
    # 22 of the 64 total bits exist in:
    pid_bits = 5
    seed_bits = 5
    sequence_bits = 12

    # define the maximum allowed seed values based on defined bits
    max_pid = -1 ^ (-1 << pid_bits)
    max_seed = -1 ^ (-1 << seed_bits)
    sequence_mask = -1 ^ (-1 << sequence_bits)

    # bit position where the process ID can be found in the snowflake
    pid_shift = sequence_bits

    # bit position where the seed value can be found in the snowflake
    seed_shift = sequence_bits + pid_bits

    # left-hand bit position where the timestamp can be found
    timestamp_shift = sequence_bits + pid_bits + seed_bits

    # enforce maximum integers allowed on provided seed values
    assert pid >= 0 and pid <= max_pid
    assert seed >= 0 and seed <= max_seed

    # if all is well, pyflake_generator creation begins

    # local pyflake_generator variables
    last_timestamp = -1
    sequence = 0

    # this process will loop 'while true' until a yield statement is
    # reached, at which time the loop will be paused pending a call to
    # `next(<generator>)`, which will return a string value and increment
    # the sequence. Multiple unique IDs may be crafted from a single
    # pyflake_generator instance, and near-infinite unique IDs may be
    # generated by utilizing multiple pyflake_generator instances
    while True:
        timestamp = math.floor(time.time() * 1000)

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
        yield (
            # subtract the current timestamp from the defined epoch, which
            # returns the miliseconds passed since the epoch time, and place
            # the timestamp value in the sequence relative to the defined
            # 'timestamp_shift' bit value defined above
            ((timestamp-epoch) << timestamp_shift) |
            # the same is done to the seed and pid values for sequence placement
            (seed << seed_shift) |
            (pid << pid_shift) |
            # finally, the current sequence value is returned, preventing race
            # conditions and ensuring uniqueness across IDs generated within
            # the same millisecond
            sequence)

# a snowflake pyflake_generator client class
# use of this class is not required - a pyflake_generator may be created by
# calling the global `pyflake_generator` function above
# the below class just makes managing the generator that much easier
class PyflakeClient():
    def __init__(self, epoch, pid, seed):
        self.epoch = epoch

        # process ID and a random generated integer are used as seed values
        # for the client pyflake_generator
        # since the maximum bits for both is 5, the value cannot be greater
        # than (2^5-1), or 31
        self.generator = pyflake_generator(self.epoch, pid, seed)

    # destroys the current pyflake_generator, if one exists
    def destroy(self):
        if getattr(self, 'generator', None):
            delattr(self, 'generator')

    # creates a new pyflake_generator, if one does not exist
    def create(self, pid, seed):
        if not getattr(self, 'generator', None):
            setattr(self, 'generator', pyflake_generator(self.epoch, pid, seed))

    # replaces the current pyflake_generator with a new one, and allows
    # the requesting client to define a process ID and seed value
    def renew(self, pid, seed):
        self.destroy()
        self.create(pid, seed)

    # shortcut function, quickly returns a snowflake ID from the attached
    # pyflake_generator, based on timestamp value at the time the request
    # was made
    def generate(self):
        return next(self.generator)

    def to_timestamp(self, id, fmt = 'ms'):
        return to_timestamp(self.epoch, id, fmt)

if __name__ == '__main__':
    sys.argv = sys.argv[1:]
    length = len(sys.argv)
    if length == 3:
        epoch = int(sys.argv[0])
        pid = int(sys.argv[1])
        seed = int(sys.argv[2])
        # generate a client for testing purposes
        client = PyflakeClient(epoch, pid, seed)

        # generate an ID to see if things are working
        id = client.generate()

        # print it out, see what it looks like
        print(id)

        # convert the generated ID into a timestamp to see if things are working
        timestamp = client.to_timestamp(id)

        # print it out, see what it looks like
        print(timestamp)

        # destroy and create the generator attached to the client
        client.renew(generate_seed(5), generate_seed(5))

        # log that something was done so the requesting client doesn't think it's stopped
        print(f'Successfully renewed generator!')

        # test the processes again to make sure they still work
        id = client.generate()

        # print it out, make sure it still looks good
        print(id)

        # convert the new ID into a timestamp to see if things are still working
        timestamp = client.to_timestamp(id)
 
        # print it out, make sure it still looks good
        print(timestamp)

        # if we made it this far, the script ran successfully without any errors
        print(f'Test completed successfully! Exiting with code (1).')
        sys.exit(1)
    else:
        raise ValueError(f'Arguments must contain:\n[0] - epoch [1 << 42]\n[1] - pid [1 << 47]\n[2] - seed [1 << 52]\n\nTotal arguments received: {length}')
