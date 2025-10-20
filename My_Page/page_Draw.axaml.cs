
#if true // TCP 是 1 UDP 是 0
#define TCP 
#else
#define UDP
#endif

using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Threading;
using Clairvoyance;
using Clairvoyance.My_class;
using DocumentFormat.OpenXml.Drawing;
using Newtonsoft.Json;
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Timers;
using static System.Diagnostics.Debugger;

namespace My_Page
{
    public partial class page_Draw : UserControl
    {
        #region 私有成員變數

        #region 計時器與執行續規劃函數

        // 繪圖更新計時器 (同步計時器)
        private DispatcherTimer? DTim_UiChar;

        // UI 元件 計時器 (異步計時器)
        private System.Threading.Timer? Tim_UiFlat;

        // 設定為 1 表示只允許一次一個進入，上面計時器的鎖
        private readonly SemaphoreSlim _timFlatLock = new(1, 1);

        private float KHZ = 0;

        #endregion

        #region 新增: SOCKET_Link 實例和快取

        #if TCP

        private TTC_Link_TCP tcp_link;

        #elif UDP

        private TTC_Link_UDP udp_link;

        #endif
        
        #endregion

        #region 檔案寫入

        private Data_Down self_Down = null;

        #endregion

        #endregion

        #region 初始化方法

        /// <summary>
        /// 建構方法
        /// </summary>
        public page_Draw()
        {
            #region 初始化方法

            // 載入 axaml UI 介面
            InitializeComponent();
            Init();

            #endregion
        }

        /// <summary>
        /// 優化後的初始化方法
        /// </summary>
        private async void Init()
        {
            #region 計時器初始化

            // 同步計時器初始化 - 增加繪圖更新頻率
            DTim_UiChar = new DispatcherTimer
            {
                Interval = TimeSpan.FromMilliseconds(50) // 從 100ms 改為 50ms 提高響應性
            };
            DTim_UiChar.Tick += DTim_UiChar_Tick;
            DTim_UiChar.Start();

            // 初始化 Timer - 降低 UI 更新頻率，因為現在有背景掃描
            Tim_UiFlat = new System.Threading.Timer(async _ =>
            {
                await OnTim_UiFlat_TickAsync(); // 呼叫非同步處理函數
            }, null, TimeSpan.FromSeconds(1), TimeSpan.FromSeconds(2)); // 從 350ms 改為 2秒

            #endregion

            #region UI 元件初始化

            Bu_CNCXYZ.Click += Bu_CNCXYZ_ClickAsync;


            // 設定預設選項為「可選」
            CB_AllRouterLink.SelectedIndex = 0;

            // 使用 lambda 處理選擇事件，強制選回「可選」
            CB_AllRouterLink.SelectionChanged += (_, e) =>
            {
                if (CB_AllRouterLink.SelectedIndex != 0)
                    CB_AllRouterLink.SelectedIndex = 0;
            };

            Task task = new Task(() => CheckIpsAsync(new string[] { "192.168.51.1", "192.168.51.2", "192.168.51.3", "192.168.51.4" }, 300));
            
            task.Start();

            #endregion

            #region 新增: 初始化 TTC_Link

            try
            {
                Bu_TTCLink.Click += Bu_TTCLink_Click_Down;

                Console.WriteLine("TTC_Link 初始化完成，背景掃描已啟動");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"TTC_Link 初始化錯誤: {ex.Message}");
                Break();
            }

            #endregion

            
        }

        /// <summary>
        /// 高速檢查多個 IP 是否可達
        /// </summary>
        /// <param name="ips">要檢查的 IP 陣列</param>
        /// <param name="timeoutMs">逾時 (毫秒)，預設 500ms</param>
        /// <returns>Task</returns>
        public async Task CheckIpsAsync(string[] ips, int timeoutMs = 500)
        {
            var aliveIps = new ConcurrentBag<string>();
            var tasks = new Task[ips.Length];

            for (int i = 0; i < ips.Length; i++)
            {
                string ip = ips[i];
                tasks[i] = Task.Run(async () =>
                {
                    try
                    {
                        using var ping = new Ping();
                        var reply = await ping.SendPingAsync(ip, timeoutMs);

                        if (reply.Status == IPStatus.Success)
                        {
                            Console.WriteLine($"✅ {ip} 存活，延遲 {reply.RoundtripTime} ms");
                            aliveIps.Add(ip);   // 執行緒安全
                        }
                        else
                        {
                            Console.WriteLine($"❌ {ip} 無回應");
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"⚠️ {ip} 發生錯誤: {ex.Message}");
                    }
                });
            }

            await Task.WhenAll(tasks);

            // 回到 UI 執行緒更新 ComboBox
            await Dispatcher.UIThread.InvokeAsync(() =>
            {
                // 先清空再設定（避免疊加舊資料）

                var list = new List<string>();
                if (!aliveIps.IsEmpty)
                {
                    list.Add("連線路由器");
                    list.AddRange(aliveIps.OrderBy(s => s)); // 可選：排序
                }
                else
                {
                    list.Add("無可用路由器");
                }

                foreach (var ip in list)
                {
                    CB_AllRouterLink.Items.Add(ip);
                }
                CB_AllRouterLink.SelectedIndex = 0;
            });
        }


        #endregion

        OpcUaClientWrapper client = new OpcUaClientWrapper();

        #region UI 元件跟新
        private void Bu_CNCXYZ_ClickAsync(object? sender, EventArgs e)
        {
            

            _ = client.Connect();


            Console.WriteLine($"X={client.GetX()}, Y={client.GetY()}, Z={client.GetZ()}");
        }


        private void Bu_TTCLink_Click_Down(object? sender, EventArgs e)
        {
            if (La_TTCLink.Content == "連線中" || La_TTCLink.Content == "斷線中") return;
            

            if (La_TTCLink.Content == "未連線")
            {
                string s = ACB_TTCSelect.Text;
                string[] ar = s.Split('(');

                La_TTCLink.Content = "連線中";

#if TCP
                

                try
                {
                    tcp_link = new TTC_Link_TCP(ar[0]);
                }
                catch
                {
                    tcp_link = null;

                    return;
                }

                La_TTCLink.Content = "已連線";

#elif UDP

                udp_link = new TTC_Link_UDP(ar[0]);

#endif

                string k_name = "noName";
                if (ar.Length > 1)
                {
                    k_name = Regex.Replace(ar[1], @"[^A-Za-z0-9\-]", "").ToUpperInvariant(); ;
                }
                string timeStr = DateTime.Now.ToString("yyyy-MM／dd HH：mm：ss_f");

                self_Down = new Data_Down(k_name, timeStr);
            }
            else
            {
#if TCP
                La_TTCLink.Content = "斷線中";

                tcp_link.Disconnect(true, 3);
                // tcp_link = null;
                La_TTCLink.Content = "未連線";

#endif 

            }
        }

        #endregion

        #region 計時器刷新

        double X, Y, Z;

        /// <summary>
        /// 優化後的 UI 元件更新計時器 - 使用快取避免重複掃描
        /// </summary>
        private async Task OnTim_UiFlat_TickAsync()
        {
            if (!await _timFlatLock.WaitAsync(0))
                return;

            try
            {
                // 延遲一下，防止過度刷新
                var pos = CNCPosition.Instance;


                await Dispatcher.UIThread.InvokeAsync(() =>
                {
                    X = client.GetX();
                    Y = client.GetY();
                    Z = client.GetZ();

                    La_CNCXYZ.Content = $"X:{X:F2},Y:{Y:F2},Z:{Z:F2}";

                });
            }
            catch (Exception ex)
            {
                Console.WriteLine($"OnTim_UiFlat_TickAsync 錯誤：{ex.Message}");
            }
            finally
            {
                _timFlatLock.Release();
            }
        }

        /// <summary>
        /// 優化後的繪圖更新 - 添加數據獲取和顯示
        /// </summary>
        private void DTim_UiChar_Tick(object? sender, EventArgs e)
        {
            try
            {
                // 每 50ms 執行的 UI 更新邏輯

                #region 新增: 刀把數據更新

#if TCP

                if (tcp_link != null)
                {
                    try
                    {
                        // 從 TCP 連線取得數據
                        var data = tcp_link.GetArLstF64();

                        if (data != null && data.Length >= 4)
                        {
                            // 更新通道數值顯示
                            UpdateChannelValues(data);

                            // 更新圖表
                            UpdateCharts(data);

                            // 🔥 新增：檔案寫入功能
                            WriteDataToFile(data);

                            KHZ += data[0].Count / 1000.0f;
                        }
                        else if (data == null)
                        {

                        }


                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"數據更新錯誤: {ex.Message}");
                    }
                }

#elif UDP

                if (udp_link != null)
                {
                    try
                    {
                        // 從 UDP 連線取得數據
                        var data = udp_link.GetArLstF64();



                        if (data != null && data.Length >= 4)
                        {
                            // 更新通道數值顯示
                            UpdateChannelValues(data);

                            // 更新圖表
                            UpdateCharts(data);

                            // 🔥 新增：檔案寫入功能
                            WriteDataToFile(data);

                            KHZ += data[0].Count / 1000.0f;
                        }
                        else if (data == null)
                        {

                        }


                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"數據更新錯誤: {ex.Message}");
                    }
                }

#endif

                #endregion

                #region 新增: 時間戳記更新

                if (TB_時間戳記 != null)
                {
                    TB_時間戳記.Text = DateTime.Now.ToString("yyyy/MM/dd HH:mm:ss");
                }

                #endregion
            }
            catch (Exception ex)
            {
                Console.WriteLine($"DTim_UiChar_Tick 錯誤: {ex.Message}");
            }

        }

        #endregion

        #region 新增: 數據更新輔助函數

        /// <summary>
        /// 更新通道數值顯示
        /// </summary>
        private void UpdateChannelValues(List<double>[] data)
        {
            try
            {
                if (data.Length >= 4)
                {
                    // 取最新值並顯示
                    if (data[0].Any() && LA_ch1_value != null)
                        LA_ch1_value.Content = data[0].Last().ToString("F3");

                    if (data[1].Any() && LA_ch2_value != null)
                        LA_ch2_value.Content = data[1].Last().ToString("F3");

                    if (data[2].Any() && LA_ch3_value != null)
                        LA_ch3_value.Content = data[2].Last().ToString("F3");

                    if (data[3].Any() && LA_ch4_value != null)
                        LA_ch4_value.Content = data[3].Last().ToString("F3");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"更新通道數值錯誤: {ex.Message}");
            }
        }

        /// <summary>
        /// 更新圖表
        /// </summary>
        private void UpdateCharts(List<double>[] data)
        {
            try
            {
                try
                {
                    if (data == null || data.Length < 4)
                        return;

                    // 🔥 降採樣並轉換：List<double> → 降採樣 → List<float>
                    var ch1Data = DownsampleAndConvert(data[0], 5);
                    var ch2Data = DownsampleAndConvert(data[1], 5);
                    var ch3Data = DownsampleAndConvert(data[2], 5);
                    var ch4Data = DownsampleAndConvert(data[3], 5);

                    // 更新各通道圖表
                    if (ch1Data?.Count > 0) sk_ch1?.添加多筆數據點(ch1Data);
                    if (ch2Data?.Count > 0) sk_ch2?.添加多筆數據點(ch2Data);
                    if (ch3Data?.Count > 0) sk_ch3?.添加多筆數據點(ch3Data);
                    if (ch4Data?.Count > 0) sk_ch4?.添加多筆數據點(ch4Data);

                    // 更新花瓣圖
                    if (ch1Data?.Count > 0 && ch2Data?.Count > 0)
                    {
                        sk_fp1?.添加多筆座標點(ch1Data, ch2Data);
                    }

                    if (ch3Data?.Count > 0 && ch4Data?.Count > 0)
                    {
                        sk_fp2?.添加多筆座標點(ch3Data, ch4Data);
                    }

                    sk_ch1.重畫畫布();
                    sk_ch2.重畫畫布();
                    sk_ch3.重畫畫布();
                    sk_ch4.重畫畫布();

                    sk_fp1.重畫畫布();
                    sk_fp2.重畫畫布();

                    // 🔥 可選：顯示降採樣資訊
                    Console.WriteLine($"📊 資料降採樣：原始 {data[0]?.Count} 點 → 降採樣後 {ch1Data?.Count} 點");
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"更新圖表錯誤: {ex.Message}");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"更新圖表錯誤: {ex.Message}");
            }
        }


        /// <summary>
        /// 將數據寫入檔案
        /// </summary>
        /// <param name="data">4通道數據陣列</param>
        private void WriteDataToFile(List<double>[] data)
        {
            try
            {
                string re = "";
                // 🔥 檢查檔案寫入器是否已初始化
                if (self_Down == null)
                {
                    // 如果還沒按連線按鈕，就不寫檔案
                    return;
                }

                // 🔥 檢查數據是否有效
                if (data == null || data.Length < 4)
                    return;

                int lo = Math.Min( Math.Min(data[0].Count, data[1].Count),  Math.Min( data[2].Count, data[3].Count));

                for(int i = 0; i < lo ; i++) 
                {
                    re += $"\n{data[0][i]},{data[1][i]},{data[2][i]},{data[3][i]},{client.GetX()},{client.GetY()},{client.GetZ()}";
                }

                self_Down.Write(re);

            }
            catch (Exception ex)
            {
                Console.WriteLine($"檔案寫入錯誤: {ex.Message}");
            }
        }


        /// <summary>
        /// 資料降採樣並轉換為 float
        /// 將每 sampleSize 個點平均為 1 個點
        /// </summary>
        /// <param name="sourceData">原始資料</param>
        /// <param name="sampleSize">每組平均的點數（預設100）</param>
        /// <returns>降採樣後的 float 列表</returns>
        private List<float> DownsampleAndConvert(List<double> sourceData, int sampleSize = 100)
        {
            if (sourceData == null || sourceData.Count == 0)
                return new List<float>();

            // 如果資料量小於採樣大小，直接轉換
            if (sourceData.Count <= sampleSize)
            {
                return sourceData.Select(x => (float)x).ToList();
            }

            var result = new List<float>();

            // 🔥 按組進行平均降採樣
            for (int i = 0; i < sourceData.Count; i += sampleSize)
            {
                int endIndex = Math.Min(i + sampleSize, sourceData.Count);
                int groupSize = endIndex - i;

                // 計算這一組的平均值
                double sum = 0;
                for (int j = i; j < endIndex; j++)
                {
                    sum += sourceData[j];
                }

                double average = sum / groupSize;

                // 🔥 檢查範圍並轉換為 float
                if (average > float.MaxValue)
                    result.Add(float.MaxValue);
                else if (average < float.MinValue)
                    result.Add(float.MinValue);
                else
                    result.Add((float)average);
            }

            return result;
        }

        #endregion

        #region 新增: 資源清理

        /// <summary>
        /// 清理資源
        /// </summary>
        protected override void OnDetachedFromVisualTree(VisualTreeAttachmentEventArgs e)
        {
            try
            {
                // 停止計時器
                DTim_UiChar?.Stop();
                Tim_UiFlat?.Dispose();

                // 清理 TTC_Link 資源
                //_ttcLink?.Dispose();


                // 清理鎖
                _timFlatLock?.Dispose();
            }
            catch (Exception ex)
            {
                Console.WriteLine($"資源清理錯誤: {ex.Message}");
            }

            base.OnDetachedFromVisualTree(e);
        }

        #endregion

    }
}