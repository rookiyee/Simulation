using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Opc.Ua;
using Opc.Ua.Client;
using Opc.Ua.Configuration;

namespace Clairvoyance.My_class
{
    public class CNCPosition
    {
        public float CNC_X { get; private set; }
        public float CNC_Y { get; private set; }
        public float CNC_Z { get; private set; }

        private static readonly CNCPosition _instance = new CNCPosition();
        public static CNCPosition Instance => _instance;

        private CNCPosition() { }

        public void Update(string axis, object value)
        {
            if (value == null) return;

            try
            {
                float floatValue = Convert.ToSingle(value);

                switch (axis)
                {
                    case "X": CNC_X = floatValue; break;
                    case "Y": CNC_Y = floatValue; break;
                    case "Z": CNC_Z = floatValue; break;
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"⚠️ 座標更新失敗: {axis}, {ex.Message}");
            }
        }
    }

    class Program
    {
        private const string Endpoint = "opc.tcp://192.168.1.112:4840";
        private const string Username = "OpcUaClient";
        private const string Password = "432432432";

        // 節點ID定義
        private static readonly Dictionary<string, string> NodeIds = new Dictionary<string, string>
        {
            {"X", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,1]"},
            {"Y", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,2]"},
            {"Z", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,3]"}
        };

        static async Task Main(string[] args)
        {
            try
            {
                await ConnectAndSubscribe();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"程式執行錯誤: {ex.Message}");
            }

            Console.WriteLine("按任意鍵退出...");
            Console.ReadKey();
        }

        private static async Task ConnectAndSubscribe()
        {
            var applicationConfiguration = new ApplicationConfiguration
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

            await applicationConfiguration.Validate(ApplicationType.Client);

            var application = new ApplicationInstance
            {
                ApplicationName = "OPC UA Client",
                ApplicationType = ApplicationType.Client,
                ApplicationConfiguration = applicationConfiguration
            };

            bool certOk = await application.CheckApplicationInstanceCertificate(false, 0);
            if (!certOk)
            {
                throw new Exception("應用程式證書檢查失敗");
            }

            var endpointDescription = CoreClientUtils.SelectEndpoint(Endpoint, false);
            var endpointConfiguration = EndpointConfiguration.Create(applicationConfiguration);
            var endpoint = new ConfiguredEndpoint(null, endpointDescription, endpointConfiguration);

            var userIdentity = new UserIdentity(Username, Password);

            var session = await Session.Create(
                applicationConfiguration,
                endpoint,
                false,
                false,
                applicationConfiguration.ApplicationName,
                30 * 60 * 1000,
                userIdentity,
                null
            );

            Console.WriteLine($"✅ 已成功連線到 OPC UA 伺服器: {Endpoint}");

            try
            {
                foreach (var (axis, nodeId) in NodeIds)
                {
                    try
                    {
                        var value = session.ReadValue(nodeId);
                        CNCPosition.Instance.Update(axis, value.Value);
                        Console.WriteLine($"目前 {axis} = {value.Value}");
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"讀取 {axis} 失敗: {ex.Message}");
                    }
                }

                var subscription = new Subscription(session.DefaultSubscription)
                {
                    PublishingInterval = 500,
                    KeepAliveCount = 10,
                    LifetimeCount = 100
                };

                session.AddSubscription(subscription);
                await subscription.CreateAsync();

                var monitoredItems = new List<MonitoredItem>();
                foreach (var (axis, nodeId) in NodeIds)
                {
                    var monitoredItem = new MonitoredItem(subscription.DefaultItem)
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

                subscription.AddItems(monitoredItems);
                await subscription.ApplyChangesAsync();

                Console.WriteLine("📡 已訂閱 X/Y/Z 三軸數值（按任意鍵可結束）");

                Console.ReadKey(true);

                await subscription.DeleteAsync(true);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"錯誤: {ex.Message}");
            }
        }

        private static void OnDataChangeNotification(MonitoredItem item, MonitoredItemNotificationEventArgs e)
        {
            foreach (var value in item.DequeueValues())
            {
                CNCPosition.Instance.Update(item.DisplayName, value.Value);
                Console.WriteLine($"🔄 {item.DisplayName} 更新: {value.Value}");
            }
        }
    }
}
