import FrontendConfig
import os
import errno
import subprocess

def relaunch():
    pass

def test_http():
    pass

def wd_log( s ):
    print "WATCHDOG: " % (s,)

if __name__ == '__main__':
    try:
        with open( FrontendConfig.PIDFILE, "r") as f:
            pid = int( f.read().split()[0] )
        if pid <= 0:
            raise ValueError
        # send signal 0 to the frontend process to check if its alive
        os.kill( pid, 0 )
        test_http()
    except IOError as ioe:
        wd_log( "Cannot open pidfile. Assuming Frontend is not running. Relaunching..." )
        relaunch()
    except ValueError as ve:
        wd_log( "Read PID is invalid! This is critical, most likely the frontend is bugging out." )
    except OSError as ose:
        if ose.errno == errno.ESRCH or ose.errno == errno.EINVAL:
            # no such process
            wd_log( "" )
            pass
        elif ose.errno == errno.EPERM:
            # we don't have permission to send a signal to the process, but clearly its alive...
            wd_log( "" )

