using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Opc.Ua;
using Opc.Ua.Client;
using Opc.Ua.Configuration;

namespace Clairvoyance.My_class
{
    public class OpcUaClientWrapper
    {
        private const string Endpoint = "opc.tcp://192.168.1.112:4840";
        private const string Username = "OpcUaClient";
        private const string Password = "432432432";

        private readonly Dictionary<string, string> NodeIds = new Dictionary<string, string>
        {
            {"X", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,1]"},
            {"Y", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,2]"},
            {"Z", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,3]"}
        };

        private ApplicationConfiguration _config;
        private Session _session;
        private Subscription _subscription;

        private double _x, _y, _z;

        public double GetX() => _x;
        public double GetY() => _y;
        public double GetZ() => _z;

        public async Task Connect()
        {
            _config = new ApplicationConfiguration
            {
                ApplicationName = "OPC UA Client",
                ApplicationUri = Utils.Format(@"urn:localhost:OPCUAClient:{0}", System.Net.Dns.GetHostName()),
                ProductUri = "https://github.com/OPCFoundation/UA-.NETStandard",
                ApplicationType = ApplicationType.Client,
                SecurityConfiguration = new SecurityConfiguration
                {
                    ApplicationCertificate = new CertificateIdentifier
                    {
                        StoreType = @"Directory",
                        StorePath = @"%CommonApplicationData%\OPC Foundation\CertificateStores\MachineDefault"
                    },
                    TrustedIssuerCertificates = new CertificateTrustList
                    {
                        StoreType = @"Directory",
                        StorePath = @"%CommonApplicationData%\OPC Foundation\CertificateStores\UA Certificate Authorities"
                    },
                    TrustedPeerCertificates = new CertificateTrustList
                    {
                        StoreType = @"Directory",
                        StorePath = @"%CommonApplicationData%\OPC Foundation\CertificateStores\UA Applications"
                    },
                    RejectedCertificateStore = new CertificateTrustList
                    {
                        StoreType = @"Directory",
                        StorePath = @"%CommonApplicationData%\OPC Foundation\CertificateStores\RejectedCertificates"
                    },
                    AutoAcceptUntrustedCertificates = true
                },
                TransportConfigurations = new TransportConfigurationCollection(),
                TransportQuotas = new TransportQuotas { OperationTimeout = 60000 },
                ClientConfiguration = new ClientConfiguration { DefaultSessionTimeout = 60000 }
            };

            await _config.Validate(ApplicationType.Client);

            var application = new ApplicationInstance
            {
                ApplicationName = "OPC UA Client",
                ApplicationType = ApplicationType.Client,
                ApplicationConfiguration = _config
            };

            bool certOk = await application.CheckApplicationInstanceCertificate(false, 0);
            if (!certOk)
                throw new Exception("應用程式證書檢查失敗");

            var endpointDescription = CoreClientUtils.SelectEndpoint(Endpoint, false);
            var endpointConfiguration = EndpointConfiguration.Create(_config);
            var endpoint = new ConfiguredEndpoint(null, endpointDescription, endpointConfiguration);

            var userIdentity = new UserIdentity(Username, Password);

            _session = await Session.Create(
                _config,
                endpoint,
                false,
                false,
                _config.ApplicationName,
                30 * 60 * 1000,
                userIdentity,
                null
            );

            Console.WriteLine($"✅ 已成功連線到 OPC UA 伺服器: {Endpoint}");

            // 建立訂閱
            _subscription = new Subscription(_session.DefaultSubscription)
            {
                PublishingInterval = 500,
                KeepAliveCount = 10,
                LifetimeCount = 100
            };

            _session.AddSubscription(_subscription);
            await _subscription.CreateAsync();

            var monitoredItems = new List<MonitoredItem>();
            foreach (var (axis, nodeId) in NodeIds)
            {
                var monitoredItem = new MonitoredItem(_subscription.DefaultItem)
                {
                    DisplayName = axis,
                    StartNodeId = nodeId,
                    AttributeId = Attributes.Value,
                    SamplingInterval = 500,
                    QueueSize = 10,
                    DiscardOldest = true
                };

                monitoredItem.Notification += OnDataChangeNotification;
                monitoredItems.Add(monitoredItem);
            }

            _subscription.AddItems(monitoredItems);
            await _subscription.ApplyChangesAsync();

            Console.WriteLine("📡 已訂閱 X/Y/Z 三軸數值");
        }

        public async Task Disconnect()
        {
            if (_subscription != null)
            {
                await _subscription.DeleteAsync(true);
                _subscription = null;
            }

            if (_session != null)
            {
                _session.Close();
                _session.Dispose();
                _session = null;
            }

            Console.WriteLine("🔌 已斷線");
        }

        private void OnDataChangeNotification(MonitoredItem monitoredItem, MonitoredItemNotificationEventArgs e)
        {
            try
            {
                foreach (var value in monitoredItem.DequeueValues())
                {
                    switch (monitoredItem.DisplayName)
                    {
                        case "X": _x = Convert.ToDouble(value.Value); break;
                        case "Y": _y = Convert.ToDouble(value.Value); break;
                        case "Z": _z = Convert.ToDouble(value.Value); break;
                    }
                    Console.WriteLine($"[訂閱] {monitoredItem.DisplayName} -> {value.Value}");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"處理數據變化時發生錯誤: {ex.Message}");
            }
        }
    }
}
