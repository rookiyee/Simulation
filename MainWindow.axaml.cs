using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Threading;
using System;
using System.Diagnostics;
using static System.Diagnostics.Debugger;

namespace Clairvoyance
{
    public partial class MainWindow : Window
    {
        public MainWindow()
        {
            InitializeComponent();

#if DEBUG // Debug 時小視窗比較方便，執行檔還是一樣一開始設定佔領使用者屏幕
            // 還原視窗
            this.WindowState = WindowState.Normal;
            this.Topmost = false;
            TB_fullscreen.Text = "🗖";
#else

            Position = new PixelPoint(0, 0); // 固定顯示在螢幕左上角

            // 預設為全螢幕
            this.WindowState = WindowState.FullScreen;
            this.Topmost = true;

            Bd_ResizeLeft.PointerPressed += (s, e) => BeginResizeDrag(WindowEdge.West, e);
            Bd_ResizeRight.PointerPressed += (s, e) => BeginResizeDrag(WindowEdge.East, e);
            Bd_ResizeBottom.PointerPressed += (s, e) => BeginResizeDrag(WindowEdge.South, e);

#endif


        }


        // Grid 視窗拖移
        private void Grid__PointerPressed(object? sender, PointerPressedEventArgs e)
        {
            BeginMoveDrag(e);
        }

        // 程式關閉按鈕
        private async void Bu_close_Click(object? sender, RoutedEventArgs e)
        {
            try
            {
                await Dispatcher.UIThread.InvokeAsync(() =>
                {
                    Close();
                });
            }
            catch (Exception ex)
            {
                // 若 UIThread 無法執行（例如已崩潰），則強制終止
                System.Diagnostics.Process.GetCurrentProcess().Kill();
            }
        }

        // 全螢幕按鈕點擊事件
        private void Bu_PostProcess_Click(object? sender, RoutedEventArgs e)
        {

            //ProcessStartInfo psi = new ProcessStartInfo(@"C:\MyApp.exe")
            string exePath = System.IO.Path.Combine(AppContext.BaseDirectory, "User_data", "MyApp.exe");

            ProcessStartInfo psi = new ProcessStartInfo(exePath)
            {
                UseShellExecute = true
            };

            Process.Start(psi);
        }

        // 全螢幕按鈕點擊事件
        private void Bu_full_screen_Click(object? sender, RoutedEventArgs e)
        {
            if (sender is Button btn && btn.Content is TextBlock txt)
            {
                if (txt.Text == "🗖")
                {
                    // 切換為全螢幕
                    this.WindowState = WindowState.FullScreen;
                    this.Topmost = true;
                    txt.Text = "🗗"; // 更換圖示
                }
                else
                {
                    // 還原視窗
                    this.WindowState = WindowState.Normal;
                    this.Topmost = false;
                    txt.Text = "🗖"; // 更換圖示
                }

                // 這裡也可以加你原本想觸發的功能
                // MyOriginalFunction();
            }
        }

        private void ResizeLeft(object? sender, PointerPressedEventArgs e)
        {
            BeginResizeDrag(WindowEdge.West, e);
        }

        private void ResizeRight(object? sender, PointerPressedEventArgs e)
        {
            BeginResizeDrag(WindowEdge.East, e);
        }

        private void ResizeBottom(object? sender, PointerPressedEventArgs e)
        {
            BeginResizeDrag(WindowEdge.South, e);
        }
    }
}
