using Opc.Ua;
using Opc.Ua.Client;
using Opc.Ua.Configuration;
using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using static System.Diagnostics.Debugger;

namespace Clairvoyance.My_class
{
    public class CNC_SINUMERIK
    {
        private const string Endpoint = "opc.tcp://192.168.1.112:4840";
        private const string Username = "OpcUaClient";
        private const string Password = "432432432";

        public static float CNC_X = 10000;
        public static float CNC_Y = 10000;
        public static float CNC_Z = 10000;

        // 節點ID定義
        private static readonly Dictionary<string, string> NodeIds = new Dictionary<string, string>
        {
            {"X", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,1]"},
            {"Y", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,2]"},
            {"Z", "ns=2;s=/Channel/GeometricAxis/actProgPos[u1,3]"}
        };

        public CNC_SINUMERIK()
        {
            Init();
        }
        public static async Task Init()
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
            // 創建應用配置
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

            // 驗證配置
            await applicationConfiguration.Validate(ApplicationType.Client);

            // 創建應用實例
            var application = new ApplicationInstance
            {
                ApplicationName = "OPC UA Client",
                ApplicationType = ApplicationType.Client,
                ApplicationConfiguration = applicationConfiguration
            };

            // 檢查並安裝證書（如果需要）
            bool certOk = await application.CheckApplicationInstanceCertificate(false, 0);
            if (!certOk)
            {
                throw new Exception("應用程式證書檢查失敗");
            }

            // 選擇端點
            var endpointDescription = CoreClientUtils.SelectEndpoint(Endpoint, false);
            var endpointConfiguration = EndpointConfiguration.Create(applicationConfiguration);
            var endpoint = new ConfiguredEndpoint(null, endpointDescription, endpointConfiguration);

            // 設置用戶憑證
            var userIdentity = new UserIdentity(Username, Password);

            // 創建會話對象
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
                

                // 讀取節點初始值
                foreach (var (axis, nodeId) in NodeIds)
                {
                    try
                    { 
                        var value = session.ReadValue(nodeId);
                        if (axis == "X")
                        {
                            CNC_X = float.Parse(value.ToString());
                        }
                        else if (axis == "Y")
                        {
                            CNC_Y = float.Parse(value.ToString());
                        }
                        else if (axis == "Z")
                        {
                            CNC_Z = float.Parse(value.ToString());
                        }
                        else 
                        {
                            Break();
                        }


                            Console.WriteLine($"目前{axis} = {value}");
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"讀取 {axis} 失敗: {ex.Message}");
                    }
                }

                // 創建訂閱
                var subscription = new Subscription(session.DefaultSubscription)
                {
                    PublishingInterval = 500,
                    KeepAliveCount = 10,
                    LifetimeCount = 100
                };

                session.AddSubscription(subscription);
                await subscription.CreateAsync();

                // 添加監控項目
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

                // 取消訂閱並斷開連接
                await subscription.DeleteAsync(true);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"發生錯誤: {ex.Message}");
            }
            finally
            {
                session.Close();
                session.Dispose();
                Console.WriteLine("🔌 已斷線");
            }
        }

        private static void OnDataChangeNotification(MonitoredItem monitoredItem, MonitoredItemNotificationEventArgs e)
        {
            try
            {
                foreach (var value in monitoredItem.DequeueValues())
                {
                    Console.WriteLine($"[訂閱] {monitoredItem.DisplayName} -> {value.Value}");

                    switch (monitoredItem.DisplayName)
                    {
                        case "X":
                            CNC_X = Convert.ToSingle(value.Value);
                            break;
                        case "Y":
                            CNC_Y = Convert.ToSingle(value.Value);
                            break;
                        case "Z":
                            CNC_Z = Convert.ToSingle(value.Value);
                            break;
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"處理數據變化時發生錯誤: {ex.Message}");
            }
        }


    }
}
