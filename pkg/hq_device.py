"""Device for hqWinterCreditAdapter"""
from distutils.debug import DEBUG
import functools
from tempfile import TemporaryFile
from time import time
from gateway_addon import Device
from hydroqc.webuser import WebUser
import hydroqc.error as HQerror
from pkg.hq_data_class import hq_Datas
import asyncio
from datetime import datetime, timedelta
from pkg.hq_property import *

#TODO: work with loop asyncio

#_POLL_INTERVAL = 5 #interval to check if data changed
print = functools.partial(print, flush=True)#allow direct print to log of gateway

class hq_Device(Device):
    """HQ winter Credit Device"""

    def __init__(self, adapter, _id, config):
        """
        Initialize the object
        
        adapter -- Adapter managing this device
        _id -- ID of this device
        config -- contract settings
        """

        Device.__init__(self, adapter, _id,)
        #TODO:
        #-fix error: 2022-02-24 18:47:22.972 ERROR  : Error getting thing description for thing with id hydroqc-garage: Error: Unable to find thing with id: hydroqc-garage
        #at /home/node/webthings/gateway/build/webpack:/src/models/things.js:268:1 when we delete the device
        #-fix error : Failed to get property ActiveEvent: getProperty: device: hydroqc-maison not found.

        #TODO:
        # -long loop feature to update date from HQ few time a day
        # -small loop feature to check time few time a min to for bool activation
        
        #setting the log level
        if self.adapter.verbose:
            log_level = "DEBUG"
        else:
            log_level = None
        self.config = config
        self.datas = hq_Datas
        self.new_datas = hq_Datas
        self._type.append('BinarySensor')
        self.description = 'Hydro Quebec Winter Credit Event 1'#not sure where it'S used
        self.title = _id#This appear in the text bar when adding the device and is the default name of the device
        self._webuser = WebUser(config['username'], config['password'],False, log_level=log_level,  http_log_level=log_level)
        self.name = _id

        self.pull_data()#get initial data
        self.init_propertys()#initialize property
        self.update_calculated_property()

    def pull_data(self):
        """
        get initial data from hq server
        """
        asyncio.run(self.async_run([self._webuser.get_info, self.get_data]))
    
    def update_hq_datas(self):
        """
        update datas if changed
        """

        if self.data_changed():
            self.datas = self.new_datas
            for property in self.properties:
                if self.get_property(property) == 'LastSync':
                    self.get_property(property).set_RO_Value(property, self.datas.lastSync)
                elif self.get_property(property) == 'NextEvent':
                    self.get_property(property).set_RO_Value(property, self.datas.nextEvent)
                elif self.get_property(property) == 'creditEarned':
                    self.get_property(property).set_RO_Value(property, self.datas.credit)

    def update_calculated_property(self):
        """
        update property that are calculated
        """
        
        #Set end of event
        if self.datas.nextEvent is None:
            endEvent = None
        elif self.datas.nextEvent.hour == 6:
            endEvent = self.datas.nextEvent + timedelta(hours=3)
        elif self.datas.nextEvent.hour == 20:
            endEvent = self.datas.nextEvent + timedelta(hours=4)

        #set pre-heat starttime
        preHeatStart = self.datas.nextEvent - timedelta(minutes=self.config['preHeatDelay'])

        #set post-heat end time

        postHeatEnd = self.datas.nextEvent + timedelta(minutes=self.config['postHeatDelay'])

        for property in self.properties:
            if self.get_property(property) == 'ActiveEvent':
                self.get_property(property).set_RO_Value(property, self.get_property(property).is_active(self.datas.nextEvent, endEvent))
            elif self.get_property(property) == 'PreHeatEvent':
                self.get_property(property).set_RO_Value(property, self.get_property(property).is_active(preHeatStart, self.datas.nextEvent))
            elif self.get_property(property) == 'PostHeatEvent':
                self.get_property(property).set_RO_VAlue(property, self.get_property(property).is_active(endEvent, postHeatEnd))


    def data_changed(self):
        """
        test if HQ data have changed or not
        
        return -- bool
        """

        if self.datas.lastSync and self.new_datas.lastSync and (self.datas.lastSync < self.new_datas.lastSync):
            #if have a previous last sync and new sync and new sync is newer
            return True
        
        else:
            return False


    def init_propertys(self):
        """
        intialize device property
        """
        #active event property
        activeEvent = hq_bool_ro_property(self, 'Active Event')
        self.properties['ActiveEvent'] = activeEvent
        #activeEvent.set_RO_Value('ActiveEvent', False)

        #pre-heat property
        preHeatEvent = hq_bool_ro_property(self, 'Pre-Heat Event')
        self.properties['PreHeatEvent'] = preHeatEvent
        #preHeatEvent.set_RO_Value('PreHeatEvent', False)

        #post-heat property
        postHeatEvent = hq_bool_ro_property(self, 'Post-Heat Event')
        self.properties['PostHeatEvent'] = postHeatEvent
        #postHeatEvent.set_RO_Value('PostHeatEvent', False)

        #next event property
        nextEvent = hq_datetime_ro_property(self, 'Next Event')
        self.properties['NextEvent'] = nextEvent
        #nextEvent.set_RO_Value('NextEvent', self.datas.nextEvent)

        #last sync property
        lastSync = hq_datetime_ro_property(self, 'Last Sync')
        self.properties['LastSync'] = lastSync
        #lastSync.set_RO_Value('LastSync', self.datas.lastSync)

        #credit total property
        credit = hq_float_ro_property(self, 'Credit Earned')
        self.properties['creditEarned'] = credit
        #credit.set_RO_Value('creditEarned', self.datas.credit)

    async def async_run(self, functions):
        await self.init_session()
        for function in functions:
            await function()
        await self.close()

    async def init_session(self):
        """
        initialize hq websession
        """
        if self._webuser.session_expired:
            print("Login")
            await self._webuser.login()
        else:
            try:
                await self._webuser.refresh_session()
                print("Refreshing session")
            except HQerror.HydroQcHTTPError:
                #if refresh didn'T work, try to login
                print("Refreshing session failed, try to login")
                self._webuser.login()
        
    async def get_user_info(self):
        await self._webuser.get_info()

    async def get_data(self):
        datas = hq_Datas
        if self._webuser._hydro_client._session:
            datas.lastSync = datetime.now()
        else:
            datas.lastSync = None
        await self._webuser.get_info()
        customer = self._webuser.get_customer(self.config['customer'])
        account = customer.get_account(self.config['account'])
        contract = account.get_contract(self.config['contract'])
        wc = contract.winter_credit
        await wc.refresh_data()
        datas.credit = float(wc.raw_data['montantEffaceProjete'])
        datas.nextEvent = wc.next_critical_peak
        self.new_datas = datas
        
    async def close(self):
        await self._webuser.close_session()
    


        
        

       