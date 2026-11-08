import hidraw,hid
def forbidden(*a,**kw):raise AssertionError('Second instance attempted HID access')
hidraw.enumerate=hidraw.device=hid.enumerate=hid.device=forbidden
